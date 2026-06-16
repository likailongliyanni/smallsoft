<?php

namespace App\Services;

use App\Models\GenerationJob;
use App\Models\QuotaLog;
use App\Models\User;
use DOMDocument;
use DOMElement;
use DOMXPath;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;
use RuntimeException;
use Symfony\Component\HttpFoundation\BinaryFileResponse;
use Throwable;
use ZipArchive;

class SpreadsheetImageExportService
{
    public function __construct(private SpreadsheetImagePlanService $planner) {}

    public function export(UploadedFile $file, User $user, string $instruction, array $options = []): array
    {
        if ($user->availableGenerations() <= 0) {
            throw new RuntimeException('次数不足，请先购买额度或联系管理员添加测试次数。');
        }
        if (! class_exists(ZipArchive::class)) {
            throw new RuntimeException('服务器缺少 ZipArchive 扩展，暂时无法解析 xlsx。');
        }

        $sourcePath = $file->getRealPath();
        if (! $sourcePath || ! is_file($sourcePath)) {
            throw new RuntimeException('上传文件读取失败。');
        }

        $sourceZip = new ZipArchive();
        if ($sourceZip->open($sourcePath) !== true) {
            throw new RuntimeException('xlsx 文件无法打开，请确认文件没有损坏。');
        }

        $batchId = (string) Str::uuid();
        $workDir = $this->batchDir($user, $batchId);
        if (! is_dir($workDir) && ! mkdir($workDir, 0775, true) && ! is_dir($workDir)) {
            throw new RuntimeException('无法创建导出目录。');
        }

        $warnings = [];

        try {
            $sheets = $this->readWorkbook($sourceZip);
            $summary = $this->buildSummary($sheets);
            $planResult = $this->planner->makePlan($summary, $instruction, $options);
            $plan = $planResult['plan'];
            $warnings = array_merge($warnings, $planResult['warnings'] ?? []);

            $zipPath = $workDir.DIRECTORY_SEPARATOR.'result.zip';
            $manifestRows = [];
            $exported = $this->writeExportZip($sourceZip, $zipPath, $sheets, $plan, $manifestRows, $warnings);
            if ($exported['image_count'] < 1) {
                throw new RuntimeException('没有在这个 xlsx 里找到可提取的内嵌图片。');
            }

            $job = $this->consumeQuotaAndLogJob($user, [
                'batch_id' => $batchId,
                'original_name' => $file->getClientOriginalName(),
                'instruction' => $instruction,
                'plan' => $plan,
                'summary' => $summary,
                'exported' => $exported,
            ], $manifestRows, $exported, $planResult);

            return [
                'batch_id' => $batchId,
                'job_id' => $job->id,
                'download_url' => '/api/spreadsheet-images/download/'.$batchId,
                'images_count' => $exported['image_count'],
                'sheets_count' => $exported['sheet_count'],
                'plan_source' => $planResult['source'],
                'plan' => $plan,
                'manifest_preview' => array_slice($manifestRows, 0, 20),
                'warnings' => $warnings,
                'remaining_quota' => $user->fresh()->availableGenerations(),
            ];
        } finally {
            $sourceZip->close();
        }
    }

    public function download(User $user, string $batchId): BinaryFileResponse
    {
        if (! preg_match('/^[A-Za-z0-9-]+$/', $batchId)) {
            abort(404);
        }

        $zipPath = $this->batchDir($user, $batchId).DIRECTORY_SEPARATOR.'result.zip';
        abort_if(! is_file($zipPath), 404, '导出文件不存在或已经被清理。');

        return response()->download($zipPath, 'spreadsheet-images-'.$batchId.'.zip', [
            'Content-Type' => 'application/zip',
        ]);
    }

    private function readWorkbook(ZipArchive $zip): array
    {
        $sharedStrings = $this->readSharedStrings($zip);
        $sheetRefs = $this->readWorkbookSheets($zip);
        if ($sheetRefs === []) {
            throw new RuntimeException('没有读取到工作表。');
        }

        $sheets = [];
        foreach ($sheetRefs as $sheetRef) {
            $rows = $this->readSheetRows($zip, $sheetRef['path'], $sharedStrings);
            $images = $this->readSheetImages($zip, $sheetRef['path']);
            $headerRow = $this->guessHeaderRow($rows['rows'], $images);
            $headers = $this->headersForRow($rows['rows'][$headerRow] ?? [], $rows['max_col']);

            $sheets[] = [
                'name' => $sheetRef['name'],
                'path' => $sheetRef['path'],
                'rows' => $rows['rows'],
                'max_row' => $rows['max_row'],
                'max_col' => $rows['max_col'],
                'images' => $images,
                'header_row' => $headerRow,
                'headers' => $headers,
            ];
        }

        return $sheets;
    }

    private function writeExportZip(ZipArchive $sourceZip, string $zipPath, array $sheets, array $plan, array &$manifestRows, array &$warnings): array
    {
        $resultZip = new ZipArchive();
        if ($resultZip->open($zipPath, ZipArchive::CREATE | ZipArchive::OVERWRITE) !== true) {
            throw new RuntimeException('无法创建结果 zip。');
        }

        $usedPaths = [];
        $sheetCount = 0;
        $imageCount = 0;
        $globalIndex = 0;
        $rowImageIndexes = [];
        $selectedSheets = array_flip(array_map('strval', $plan['sheets'] ?? []));

        try {
            foreach ($sheets as $sheet) {
                if (($plan['sheet_mode'] ?? 'all') === 'selected' && ! isset($selectedSheets[$sheet['name']])) {
                    continue;
                }
                if (($sheet['images'] ?? []) === []) {
                    continue;
                }

                $sheetCount++;
                $headers = $sheet['headers'];
                $headerRow = (int) (($plan['header_row_by_sheet'][$sheet['name']] ?? null) ?: $sheet['header_row']);

                foreach ($sheet['images'] as $image) {
                    $bytes = $sourceZip->getFromName($image['media_path']);
                    if ($bytes === false || $bytes === '') {
                        $warnings[] = '图片读取失败：'.$sheet['name'].' '.$image['media_path'];
                        continue;
                    }

                    $matchedRow = $this->matchImageRow($sheet['rows'], $headerRow, (int) $image['row']);
                    $rowData = $this->rowToAssoc($sheet['rows'][$matchedRow] ?? [], $headers);
                    $rowKey = $sheet['name'].'#'.$matchedRow;
                    $rowImageIndexes[$rowKey] = ($rowImageIndexes[$rowKey] ?? 0) + 1;
                    $globalIndex++;

                    $placeholders = $this->placeholders($rowData, $sheet['name'], $matchedRow, $rowImageIndexes[$rowKey], $globalIndex);
                    $processed = $this->processImage($bytes, $image['media_path'], $plan['image_processing'] ?? [], $warnings);
                    $folder = $this->renderFolder((string) ($plan['folder_template'] ?? ''), $placeholders);
                    $filenameBase = $this->renderTemplate((string) ($plan['filename_template'] ?? ''), $placeholders);
                    if ($filenameBase === '') {
                        $filenameBase = $this->renderTemplate((string) ($plan['fallback_filename_template'] ?? '{sheet}_{row}_{图片序号}'), $placeholders);
                    }
                    $filenameBase = $this->sanitizePathPart($filenameBase, 'image-'.$globalIndex);
                    $filename = $filenameBase.'.'.$processed['extension'];
                    $zipEntry = $this->uniqueZipPath(trim($folder.'/'.$filename, '/'), $usedPaths);

                    $resultZip->addFromString($zipEntry, $processed['bytes']);
                    $imageCount++;

                    $manifestRows[] = [
                        'sheet' => $sheet['name'],
                        'row' => $matchedRow,
                        'image_index' => $rowImageIndexes[$rowKey],
                        'file_path' => $zipEntry,
                        'source_media' => $image['media_path'],
                        'anchor' => $this->columnLetters((int) $image['col']).$image['row'],
                        'matched_fields' => json_encode($rowData, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                    ];
                }
            }

            $resultZip->addFromString('manifest.csv', $this->csv($manifestRows));
            $resultZip->addFromString('plan.json', json_encode($plan, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT));
        } finally {
            $resultZip->close();
        }

        return [
            'sheet_count' => $sheetCount,
            'image_count' => $imageCount,
            'zip_path' => $zipPath,
        ];
    }

    private function consumeQuotaAndLogJob(User $user, array $payload, array $manifestRows, array $exported, array $planResult): GenerationJob
    {
        return DB::transaction(function () use ($user, $payload, $manifestRows, $exported, $planResult): GenerationJob {
            $fresh = User::query()->lockForUpdate()->findOrFail($user->id);
            if ($fresh->free_generations > 0) {
                $fresh->decrement('free_generations');
            } elseif ($fresh->paid_generations > 0) {
                $fresh->decrement('paid_generations');
            } else {
                throw new RuntimeException('次数不足，请先购买额度或联系管理员添加测试次数。');
            }

            $job = GenerationJob::create([
                'user_id' => $fresh->id,
                'flow_name' => Str::limit('表格图片整理：'.($payload['original_name'] ?? 'xlsx'), 120, ''),
                'status' => 'completed',
                'step_count' => (int) $exported['image_count'],
                'request_payload' => $payload,
                'result_script' => json_encode(array_slice($manifestRows, 0, 100), JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES),
                'warnings' => $planResult['warnings'] ?? [],
                'used_provider' => $planResult['used_provider'] ?? $planResult['source'] ?? null,
                'used_model' => $planResult['used_model'] ?? null,
            ]);

            QuotaLog::create([
                'user_id' => $fresh->id,
                'change_value' => -1,
                'source' => 'spreadsheet_image_export',
                'note' => '表格图片整理任务 #'.$job->id,
            ]);

            return $job;
        });
    }

    private function buildSummary(array $sheets): array
    {
        return [
            'sheets' => array_map(function (array $sheet): array {
                $samples = [];
                for ($row = $sheet['header_row'] + 1; $row <= min($sheet['max_row'], $sheet['header_row'] + 5); $row++) {
                    $assoc = $this->rowToAssoc($sheet['rows'][$row] ?? [], $sheet['headers']);
                    if ($this->hasAnyValue($assoc)) {
                        $samples[] = $assoc;
                    }
                }

                return [
                    'name' => $sheet['name'],
                    'max_row' => $sheet['max_row'],
                    'image_count' => count($sheet['images']),
                    'first_image_row' => min(array_map(fn (array $image): int => (int) $image['row'], $sheet['images'] ?: [['row' => 0]])),
                    'guessed_header_row' => $sheet['header_row'],
                    'headers' => array_values(array_filter($sheet['headers'])),
                    'sample_rows' => $samples,
                ];
            }, $sheets),
        ];
    }

    private function readWorkbookSheets(ZipArchive $zip): array
    {
        $dom = $this->domFromZip($zip, 'xl/workbook.xml');
        $rels = $this->relationships($zip, 'xl/_rels/workbook.xml.rels', 'xl/workbook.xml');

        $xp = new DOMXPath($dom);
        $xp->registerNamespace('main', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main');
        $xp->registerNamespace('r', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships');

        $sheets = [];
        foreach ($xp->query('//main:sheets/main:sheet') as $sheet) {
            if (! $sheet instanceof DOMElement) {
                continue;
            }
            $rid = $sheet->getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id');
            if ($rid === '' || empty($rels[$rid]['target'])) {
                continue;
            }

            $sheets[] = [
                'name' => $sheet->getAttribute('name') ?: 'Sheet'.(count($sheets) + 1),
                'path' => $rels[$rid]['target'],
            ];
        }

        return $sheets;
    }

    private function readSharedStrings(ZipArchive $zip): array
    {
        $xml = $zip->getFromName('xl/sharedStrings.xml');
        if ($xml === false) {
            return [];
        }

        $dom = $this->domFromString($xml);
        $xp = new DOMXPath($dom);
        $xp->registerNamespace('main', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main');

        $strings = [];
        foreach ($xp->query('//main:sst/main:si') as $si) {
            $parts = [];
            foreach ($xp->query('.//main:t', $si) as $textNode) {
                $parts[] = $textNode->textContent;
            }
            $strings[] = implode('', $parts);
        }

        return $strings;
    }

    private function readSheetRows(ZipArchive $zip, string $sheetPath, array $sharedStrings): array
    {
        $xml = $zip->getFromName($sheetPath);
        if ($xml === false) {
            return ['rows' => [], 'max_row' => 0, 'max_col' => 0];
        }

        $sheet = simplexml_load_string($xml, 'SimpleXMLElement', LIBXML_NONET);
        if (! $sheet) {
            return ['rows' => [], 'max_row' => 0, 'max_col' => 0];
        }

        $rows = [];
        $maxRow = 0;
        $maxCol = 0;

        foreach ($sheet->sheetData->row as $rowNode) {
            $rowNum = (int) ($rowNode['r'] ?? 0);
            if ($rowNum <= 0) {
                $rowNum = $maxRow + 1;
            }
            $maxRow = max($maxRow, $rowNum);

            foreach ($rowNode->c as $cell) {
                $ref = (string) ($cell['r'] ?? '');
                $col = $ref !== '' ? $this->columnNumber($ref) : count($rows[$rowNum] ?? []) + 1;
                if ($col < 1) {
                    continue;
                }
                $maxCol = max($maxCol, $col);
                $value = $this->cellValue($cell, $sharedStrings);
                if ($value !== '') {
                    $rows[$rowNum][$col] = $value;
                }
            }
        }

        ksort($rows);

        return ['rows' => $rows, 'max_row' => $maxRow, 'max_col' => $maxCol];
    }

    private function readSheetImages(ZipArchive $zip, string $sheetPath): array
    {
        $sheetXml = $zip->getFromName($sheetPath);
        if ($sheetXml === false) {
            return [];
        }

        $sheetRels = $this->relationships($zip, $this->relsPath($sheetPath), $sheetPath);
        $sheetDom = $this->domFromString($sheetXml);
        $sheetXp = new DOMXPath($sheetDom);
        $sheetXp->registerNamespace('main', 'http://schemas.openxmlformats.org/spreadsheetml/2006/main');

        $images = [];
        foreach ($sheetXp->query('//main:drawing') as $drawingNode) {
            if (! $drawingNode instanceof DOMElement) {
                continue;
            }

            $rid = $drawingNode->getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'id');
            $drawingPath = $sheetRels[$rid]['target'] ?? null;
            if (! $drawingPath) {
                continue;
            }

            $images = array_merge($images, $this->readDrawingImages($zip, $drawingPath));
        }

        usort($images, fn (array $a, array $b): int => [$a['row'], $a['col'], $a['media_path']] <=> [$b['row'], $b['col'], $b['media_path']]);

        return $images;
    }

    private function readDrawingImages(ZipArchive $zip, string $drawingPath): array
    {
        $drawingXml = $zip->getFromName($drawingPath);
        if ($drawingXml === false) {
            return [];
        }

        $rels = $this->relationships($zip, $this->relsPath($drawingPath), $drawingPath);
        $dom = $this->domFromString($drawingXml);
        $xp = new DOMXPath($dom);
        $xp->registerNamespace('xdr', 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing');
        $xp->registerNamespace('a', 'http://schemas.openxmlformats.org/drawingml/2006/main');

        $images = [];
        foreach ($xp->query('//xdr:twoCellAnchor|//xdr:oneCellAnchor') as $anchor) {
            if (! $anchor instanceof DOMElement) {
                continue;
            }

            $row = ((int) ($xp->query('./xdr:from/xdr:row', $anchor)->item(0)?->textContent ?? 0)) + 1;
            $col = ((int) ($xp->query('./xdr:from/xdr:col', $anchor)->item(0)?->textContent ?? 0)) + 1;
            $blip = $xp->query('.//a:blip', $anchor)->item(0);
            if (! $blip instanceof DOMElement) {
                continue;
            }

            $embed = $blip->getAttributeNS('http://schemas.openxmlformats.org/officeDocument/2006/relationships', 'embed');
            $mediaPath = $rels[$embed]['target'] ?? null;
            if (! $mediaPath) {
                continue;
            }

            $images[] = [
                'row' => max(1, $row),
                'col' => max(1, $col),
                'media_path' => $mediaPath,
            ];
        }

        return $images;
    }

    private function relationships(ZipArchive $zip, string $relsPath, string $baseFile): array
    {
        $xml = $zip->getFromName($relsPath);
        if ($xml === false) {
            return [];
        }

        $dom = $this->domFromString($xml);
        $xp = new DOMXPath($dom);
        $xp->registerNamespace('rel', 'http://schemas.openxmlformats.org/package/2006/relationships');

        $rels = [];
        foreach ($xp->query('//rel:Relationship') as $rel) {
            if (! $rel instanceof DOMElement) {
                continue;
            }

            $rels[$rel->getAttribute('Id')] = [
                'type' => $rel->getAttribute('Type'),
                'target' => $this->resolvePath($baseFile, $rel->getAttribute('Target')),
            ];
        }

        return $rels;
    }

    private function processImage(string $bytes, string $sourceName, array $processing, array &$warnings): array
    {
        $sourceExt = strtolower(pathinfo($sourceName, PATHINFO_EXTENSION) ?: 'jpg');
        $targetFormat = strtolower((string) ($processing['format'] ?? 'original'));
        if ($targetFormat === 'jpeg') {
            $targetFormat = 'jpg';
        }

        $shouldProcess = ! empty($processing['crop_whitespace'])
            || ! empty($processing['resize'])
            || ! empty($processing['enhance'])
            || in_array($targetFormat, ['jpg', 'png'], true);

        if (! $shouldProcess) {
            return ['bytes' => $bytes, 'extension' => $this->safeImageExtension($sourceExt)];
        }

        if (! extension_loaded('gd') || ! function_exists('imagecreatefromstring')) {
            $warnings[] = '服务器未启用 GD 图片扩展，已跳过裁剪/清晰化处理。';

            return ['bytes' => $bytes, 'extension' => $this->safeImageExtension($sourceExt)];
        }

        $image = @imagecreatefromstring($bytes);
        if (! $image) {
            $warnings[] = '图片处理失败，已保留原图：'.$sourceName;

            return ['bytes' => $bytes, 'extension' => $this->safeImageExtension($sourceExt)];
        }

        try {
            if (! empty($processing['crop_whitespace']) && function_exists('imagecropauto')) {
                $cropped = @imagecropauto($image, defined('IMG_CROP_WHITE') ? IMG_CROP_WHITE : -2);
                if ($cropped) {
                    imagedestroy($image);
                    $image = $cropped;
                }
            }

            $resize = $processing['resize'] ?? null;
            if (is_array($resize) && ! empty($resize['width']) && ! empty($resize['height'])) {
                $image = $this->resizeToCanvas($image, (int) $resize['width'], (int) $resize['height']);
            }

            if (! empty($processing['enhance'])) {
                if (function_exists('imagefilter')) {
                    @imagefilter($image, IMG_FILTER_CONTRAST, -8);
                }
                if (function_exists('imageconvolution')) {
                    @imageconvolution($image, [[0, -1, 0], [-1, 5, -1], [0, -1, 0]], 1, 0);
                }
            }

            $extension = $targetFormat === 'png' ? 'png' : ($targetFormat === 'jpg' ? 'jpg' : $this->safeImageExtension($sourceExt));
            if (! in_array($extension, ['jpg', 'jpeg', 'png', 'webp'], true)) {
                $extension = 'jpg';
            }

            ob_start();
            if ($extension === 'png') {
                imagepng($image, null, 6);
            } elseif ($extension === 'webp' && function_exists('imagewebp')) {
                imagewebp($image, null, 90);
            } else {
                imagejpeg($image, null, 92);
                $extension = 'jpg';
            }
            $processedBytes = (string) ob_get_clean();

            return ['bytes' => $processedBytes, 'extension' => $extension === 'jpeg' ? 'jpg' : $extension];
        } finally {
            imagedestroy($image);
        }
    }

    private function resizeToCanvas($image, int $targetWidth, int $targetHeight)
    {
        $targetWidth = max(1, min($targetWidth, 5000));
        $targetHeight = max(1, min($targetHeight, 5000));
        $width = imagesx($image);
        $height = imagesy($image);
        $scale = min($targetWidth / max(1, $width), $targetHeight / max(1, $height));
        $newWidth = max(1, (int) floor($width * $scale));
        $newHeight = max(1, (int) floor($height * $scale));

        $canvas = imagecreatetruecolor($targetWidth, $targetHeight);
        $white = imagecolorallocate($canvas, 255, 255, 255);
        imagefilledrectangle($canvas, 0, 0, $targetWidth, $targetHeight, $white);
        imagecopyresampled(
            $canvas,
            $image,
            (int) floor(($targetWidth - $newWidth) / 2),
            (int) floor(($targetHeight - $newHeight) / 2),
            0,
            0,
            $newWidth,
            $newHeight,
            $width,
            $height,
        );
        imagedestroy($image);

        return $canvas;
    }

    private function guessHeaderRow(array $rows, array $images): int
    {
        $firstImageRow = $images === [] ? 20 : min(array_map(fn (array $image): int => (int) $image['row'], $images));
        $limit = max(1, min(30, $firstImageRow));
        $bestRow = 1;
        $bestScore = -1;

        foreach ($rows as $rowNum => $cells) {
            if ($rowNum > $limit) {
                continue;
            }

            $values = array_filter(array_map('trim', array_map('strval', $cells)));
            $score = count($values);
            foreach ($values as $value) {
                if ($this->containsAny($value, ['货号', '款号', 'sku', '编码', '品名', '名称', '颜色', '尺码', '品牌', '分类', '图片', 'image'])) {
                    $score += 4;
                }
            }

            if ($score > $bestScore) {
                $bestScore = $score;
                $bestRow = (int) $rowNum;
            }
        }

        return max(1, $bestRow);
    }

    private function headersForRow(array $row, int $maxCol): array
    {
        $headers = [];
        for ($col = 1; $col <= max(1, $maxCol); $col++) {
            $header = trim((string) ($row[$col] ?? ''));
            $headers[$col] = $header !== '' ? $header : $this->columnLetters($col);
        }

        return $headers;
    }

    private function matchImageRow(array $rows, int $headerRow, int $anchorRow): int
    {
        $anchorRow = max($headerRow + 1, $anchorRow);
        $candidates = [$anchorRow, $anchorRow + 1, $anchorRow - 1, $anchorRow + 2, $anchorRow - 2];
        foreach ($candidates as $row) {
            if ($row > $headerRow && isset($rows[$row]) && $this->hasAnyValue($rows[$row])) {
                return $row;
            }
        }

        return $anchorRow;
    }

    private function rowToAssoc(array $row, array $headers): array
    {
        $data = [];
        foreach ($headers as $col => $header) {
            $value = trim((string) ($row[$col] ?? ''));
            if ($value !== '') {
                $data[$header] = $value;
            }
        }

        return $data;
    }

    private function placeholders(array $rowData, string $sheetName, int $row, int $rowImageIndex, int $globalIndex): array
    {
        $values = [
            'sheet' => $sheetName,
            'sheet_name' => $sheetName,
            '工作表' => $sheetName,
            'row' => (string) $row,
            '行号' => (string) $row,
            'index' => (string) $globalIndex,
            '序号' => (string) $globalIndex,
            '图片序号' => (string) $rowImageIndex,
            'image_index' => (string) $rowImageIndex,
        ];

        foreach ($rowData as $key => $value) {
            $values[$key] = (string) $value;
            $values[$this->normalizeKey($key)] = (string) $value;
        }

        foreach ([
            '货号' => ['货号', '款号', 'sku', 'SKU', '编码', '商品编码', 'item', 'code'],
            '颜色' => ['颜色', '色号', 'color'],
            '尺码' => ['尺码', '尺寸', 'size'],
            '品名' => ['品名', '名称', '商品名', 'title', 'name'],
            '品牌' => ['品牌', 'brand'],
            '分类' => ['分类', '类目', 'category'],
        ] as $canonical => $keywords) {
            $value = $this->firstMatchingValue($rowData, $keywords);
            if ($value !== '') {
                $values[$canonical] = $value;
            }
        }

        return $values;
    }

    private function firstMatchingValue(array $rowData, array $keywords): string
    {
        foreach ($rowData as $key => $value) {
            if ($this->containsAny((string) $key, $keywords) && trim((string) $value) !== '') {
                return trim((string) $value);
            }
        }

        return '';
    }

    private function renderTemplate(string $template, array $values): string
    {
        $template = trim($template);
        if ($template === '') {
            return '';
        }

        $rendered = preg_replace_callback('/\{([^}]+)\}/u', function (array $m) use ($values): string {
            $key = trim($m[1]);
            return (string) ($values[$key] ?? $values[$this->normalizeKey($key)] ?? '');
        }, $template);

        $rendered = preg_replace('/[_\-\s]+/u', '_', (string) $rendered);

        return trim($rendered, " _-\t\n\r\0\x0B");
    }

    private function renderFolder(string $template, array $values): string
    {
        $folder = $this->renderTemplate($template, $values);
        if ($folder === '') {
            return '';
        }

        $parts = preg_split('/[\/\\\\]+/u', $folder) ?: [];
        $parts = array_values(array_filter(array_map(fn (string $part): string => $this->sanitizePathPart($part, ''), $parts)));

        return implode('/', $parts);
    }

    private function uniqueZipPath(string $path, array &$usedPaths): string
    {
        $path = trim(str_replace('\\', '/', $path), '/');
        $dir = trim(dirname($path), '.');
        $name = pathinfo($path, PATHINFO_FILENAME);
        $ext = pathinfo($path, PATHINFO_EXTENSION);
        $candidate = $path;
        $i = 2;
        while (isset($usedPaths[mb_strtolower($candidate, 'UTF-8')])) {
            $candidateName = $name.'-'.$i.($ext ? '.'.$ext : '');
            $candidate = ($dir !== '' ? $dir.'/' : '').$candidateName;
            $i++;
        }
        $usedPaths[mb_strtolower($candidate, 'UTF-8')] = true;

        return $candidate;
    }

    private function sanitizePathPart(string $value, string $fallback): string
    {
        $value = trim($value);
        $value = preg_replace('/[<>:"\/\\\\|?*\x00-\x1F]+/u', '_', $value) ?: '';
        $value = preg_replace('/\s+/u', ' ', $value) ?: '';
        $value = trim($value, " ._-\t\n\r\0\x0B");
        if ($value === '') {
            $value = $fallback;
        }

        return mb_substr($value, 0, 120, 'UTF-8');
    }

    private function csv(array $rows): string
    {
        $handle = fopen('php://temp', 'r+');
        fputcsv($handle, ['sheet', 'row', 'image_index', 'file_path', 'source_media', 'anchor', 'matched_fields']);
        foreach ($rows as $row) {
            fputcsv($handle, [
                $row['sheet'] ?? '',
                $row['row'] ?? '',
                $row['image_index'] ?? '',
                $row['file_path'] ?? '',
                $row['source_media'] ?? '',
                $row['anchor'] ?? '',
                $row['matched_fields'] ?? '',
            ]);
        }
        rewind($handle);
        $csv = stream_get_contents($handle);
        fclose($handle);

        return "\xEF\xBB\xBF".$csv;
    }

    private function cellValue($cell, array $sharedStrings): string
    {
        $type = (string) ($cell['t'] ?? '');
        if ($type === 's') {
            $idx = (int) ($cell->v ?? -1);
            return trim((string) ($sharedStrings[$idx] ?? ''));
        }
        if ($type === 'inlineStr') {
            $parts = [];
            if (isset($cell->is->t)) {
                $parts[] = (string) $cell->is->t;
            }
            foreach ($cell->is->r ?? [] as $run) {
                if (isset($run->t)) {
                    $parts[] = (string) $run->t;
                }
            }

            return trim(implode('', $parts));
        }
        if ($type === 'b') {
            return ((string) ($cell->v ?? '')) === '1' ? 'TRUE' : 'FALSE';
        }

        return trim((string) ($cell->v ?? ''));
    }

    private function domFromZip(ZipArchive $zip, string $path): DOMDocument
    {
        $xml = $zip->getFromName($path);
        if ($xml === false) {
            throw new RuntimeException('xlsx 缺少必要文件：'.$path);
        }

        return $this->domFromString($xml);
    }

    private function domFromString(string $xml): DOMDocument
    {
        $previous = libxml_use_internal_errors(true);
        try {
            $dom = new DOMDocument();
            if (! $dom->loadXML($xml, LIBXML_NONET)) {
                throw new RuntimeException('XML 解析失败。');
            }

            return $dom;
        } finally {
            libxml_clear_errors();
            libxml_use_internal_errors($previous);
        }
    }

    private function resolvePath(string $baseFile, string $target): string
    {
        if ($target === '') {
            return '';
        }
        if (str_starts_with($target, '/')) {
            return ltrim($target, '/');
        }

        $baseDir = str_replace('\\', '/', dirname($baseFile));
        $path = $baseDir.'/'.$target;
        $parts = [];
        foreach (explode('/', str_replace('\\', '/', $path)) as $part) {
            if ($part === '' || $part === '.') {
                continue;
            }
            if ($part === '..') {
                array_pop($parts);
                continue;
            }
            $parts[] = $part;
        }

        return implode('/', $parts);
    }

    private function relsPath(string $path): string
    {
        return dirname($path).'/_rels/'.basename($path).'.rels';
    }

    private function columnNumber(string $cellRef): int
    {
        if (! preg_match('/^([A-Z]+)/i', $cellRef, $m)) {
            return 0;
        }

        $letters = strtoupper($m[1]);
        $num = 0;
        for ($i = 0; $i < strlen($letters); $i++) {
            $num = $num * 26 + (ord($letters[$i]) - 64);
        }

        return $num;
    }

    private function columnLetters(int $col): string
    {
        $letters = '';
        while ($col > 0) {
            $col--;
            $letters = chr(65 + ($col % 26)).$letters;
            $col = intdiv($col, 26);
        }

        return $letters ?: 'A';
    }

    private function safeImageExtension(string $extension): string
    {
        $extension = strtolower($extension);
        return in_array($extension, ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp'], true)
            ? ($extension === 'jpeg' ? 'jpg' : $extension)
            : 'jpg';
    }

    private function normalizeKey(string $key): string
    {
        return mb_strtolower(preg_replace('/[\s_：:：-]+/u', '', trim($key)) ?: '', 'UTF-8');
    }

    private function hasAnyValue(array $values): bool
    {
        foreach ($values as $value) {
            if (trim((string) $value) !== '') {
                return true;
            }
        }

        return false;
    }

    private function containsAny(string $text, array $needles): bool
    {
        $haystack = mb_strtolower($text, 'UTF-8');
        foreach ($needles as $needle) {
            if ($needle !== '' && str_contains($haystack, mb_strtolower((string) $needle, 'UTF-8'))) {
                return true;
            }
        }

        return false;
    }

    private function batchDir(User $user, string $batchId): string
    {
        return storage_path('app/private/spreadsheet-image-exporter/user-'.$user->id.'/'.$batchId);
    }
}
