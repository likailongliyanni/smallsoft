@extends('layouts.app')

@section('title', '控件训练场 - 好办法自动化')
@section('page', 'control-lab')

@section('content')
<style>
    body[data-page="control-lab"] {
        background: #f5f7fb;
    }

    .control-lab {
        --lab-border: #d8dee9;
        --lab-muted: #64748b;
        --lab-text: #1f2937;
        --lab-primary: #2563eb;
        --lab-primary-soft: #eff6ff;
        --lab-danger: #ef4444;
        max-width: 1180px;
        margin: 0 auto;
        padding: 28px 20px 56px;
        color: var(--lab-text);
    }

    .lab-head {
        display: flex;
        align-items: flex-end;
        justify-content: space-between;
        gap: 24px;
        margin-bottom: 20px;
    }

    .lab-head h1 {
        font-size: 26px;
        line-height: 1.3;
        margin: 0 0 6px;
        letter-spacing: 0;
    }

    .lab-head p {
        margin: 0;
        color: var(--lab-muted);
        font-size: 14px;
    }

    .lab-head-actions {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
    }

    .lab-shell {
        display: grid;
        grid-template-columns: minmax(0, 1fr) 340px;
        gap: 16px;
        align-items: start;
    }

    .lab-panel {
        background: #fff;
        border: 1px solid var(--lab-border);
        border-radius: 8px;
        overflow: visible;
    }

    .lab-panel-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        padding: 14px 16px;
        border-bottom: 1px solid var(--lab-border);
        background: #fbfcff;
    }

    .lab-panel-header h2 {
        margin: 0;
        font-size: 16px;
        line-height: 1.4;
    }

    .lab-panel-header span {
        color: var(--lab-muted);
        font-size: 12px;
    }

    .lab-section {
        padding: 16px;
        border-bottom: 1px solid #edf1f7;
    }

    .lab-section:last-child {
        border-bottom: 0;
    }

    .lab-section h3 {
        margin: 0 0 14px;
        font-size: 14px;
        line-height: 1.4;
        color: #0f172a;
    }

    .lab-grid {
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        column-gap: 18px;
        row-gap: 14px;
    }

    .lab-grid.full {
        grid-template-columns: 1fr;
    }

    .el-form-item {
        display: grid;
        grid-template-columns: 120px minmax(0, 1fr);
        gap: 10px;
        align-items: start;
        min-height: 40px;
        position: relative;
    }

    .el-form-item__label {
        padding-top: 9px;
        color: #374151;
        font-size: 14px;
        text-align: right;
        white-space: nowrap;
    }

    .el-form-item.is-required > .el-form-item__label::before {
        content: "* ";
        color: var(--lab-danger);
    }

    .el-form-item__content {
        min-width: 0;
        position: relative;
    }

    .el-input,
    .el-textarea {
        width: 100%;
        position: relative;
    }

    .el-input__inner,
    .el-textarea__inner,
    .lab-native-select {
        width: 100%;
        min-height: 40px;
        border: 1px solid #cfd7e6;
        border-radius: 4px;
        padding: 0 12px;
        color: #1f2937;
        background: #fff;
        font-size: 14px;
        outline: none;
        transition: border-color 0.15s, box-shadow 0.15s;
    }

    .el-textarea__inner {
        min-height: 88px;
        padding: 9px 12px;
        resize: vertical;
        line-height: 1.6;
    }

    .el-input__inner:focus,
    .el-textarea__inner:focus,
    .lab-native-select:focus {
        border-color: var(--lab-primary);
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }

    .el-input__suffix {
        position: absolute;
        right: 10px;
        top: 50%;
        transform: translateY(-50%);
        color: #94a3b8;
        pointer-events: none;
    }

    .el-select .el-input__inner,
    .el-cascader .el-input__inner {
        padding-right: 30px;
        cursor: pointer;
    }

    .lab-dropdown,
    .lab-cascader-panel,
    .lab-date-panel {
        position: absolute;
        left: 0;
        top: calc(100% + 6px);
        z-index: 50;
        min-width: 100%;
        max-height: 260px;
        overflow: auto;
        background: #fff;
        border: 1px solid #d7deea;
        border-radius: 6px;
        box-shadow: 0 12px 28px rgba(15, 23, 42, 0.14);
    }

    .lab-dropdown[hidden],
    .lab-cascader-panel[hidden],
    .lab-date-panel[hidden],
    .lab-dialog[hidden] {
        display: none !important;
    }

    .el-select-dropdown__list,
    .el-cascader-menu__list {
        list-style: none;
        margin: 0;
        padding: 6px 0;
    }

    .el-select-dropdown__item,
    .el-cascader-node {
        display: flex;
        align-items: center;
        min-height: 34px;
        padding: 0 14px;
        font-size: 14px;
        color: #334155;
        cursor: pointer;
        white-space: nowrap;
    }

    .el-select-dropdown__item:hover,
    .el-select-dropdown__item.hover,
    .el-cascader-node:hover,
    .el-cascader-node.in-active-path {
        background: var(--lab-primary-soft);
        color: #1d4ed8;
    }

    .el-select-dropdown__item.is-selected,
    .el-cascader-node.is-selected {
        color: #1d4ed8;
        font-weight: 700;
    }

    .lab-zero-placeholder {
        width: 0 !important;
        height: 0 !important;
        min-height: 0 !important;
        padding: 0 !important;
        overflow: hidden !important;
        opacity: 0 !important;
    }

    .lab-cascader-panel {
        display: grid;
        grid-template-columns: 168px 168px;
        width: 336px;
        max-height: 240px;
        overflow: hidden;
    }

    .el-cascader-menu {
        min-height: 188px;
        border-right: 1px solid #edf1f7;
        overflow: auto;
    }

    .el-cascader-menu:last-child {
        border-right: 0;
    }

    .lab-inline-options {
        display: flex;
        align-items: center;
        flex-wrap: wrap;
        gap: 14px;
        min-height: 40px;
    }

    .lab-menu-board {
        display: grid;
        grid-template-columns: minmax(240px, 320px) minmax(0, 1fr);
        gap: 14px;
        align-items: start;
    }

    .el-menu {
        list-style: none;
        margin: 0;
        padding: 6px;
        border: 1px solid #d7deea;
        border-radius: 6px;
        background: #fff;
    }

    .el-submenu,
    .el-menu-item {
        position: relative;
        min-height: 36px;
        color: #334155;
        font-size: 14px;
    }

    .el-submenu__title,
    .el-menu-item {
        display: flex;
        align-items: center;
        justify-content: space-between;
        min-height: 36px;
        padding: 0 12px;
        border-radius: 4px;
        cursor: pointer;
        user-select: none;
    }

    .el-submenu__title:hover,
    .el-menu-item:hover,
    .el-menu-item.is-active {
        background: var(--lab-primary-soft);
        color: #1d4ed8;
    }

    .el-submenu .el-menu {
        margin-top: 4px;
        margin-left: 14px;
        border-style: dashed;
    }

    .el-menu[hidden] {
        display: none !important;
    }

    .lab-tabs {
        border: 1px solid #d7deea;
        border-radius: 6px;
        background: #fff;
        overflow: hidden;
    }

    .el-tabs__header {
        display: flex;
        border-bottom: 1px solid #edf1f7;
        background: #fbfcff;
    }

    .el-tabs__item {
        min-height: 38px;
        padding: 0 16px;
        border: 0;
        border-right: 1px solid #edf1f7;
        background: transparent;
        color: #475569;
        cursor: pointer;
    }

    .el-tabs__item.is-active {
        background: #fff;
        color: #1d4ed8;
        font-weight: 700;
    }

    .el-tab-pane {
        min-height: 92px;
        padding: 12px;
        color: #475569;
        font-size: 14px;
    }

    .el-tab-pane[hidden] {
        display: none !important;
    }

    .el-radio,
    .el-checkbox {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        color: #334155;
        font-size: 14px;
        cursor: pointer;
    }

    .el-radio input,
    .el-checkbox input {
        width: 16px;
        height: 16px;
        accent-color: var(--lab-primary);
    }

    .upload-tile {
        width: 96px;
        height: 96px;
        display: grid;
        place-items: center;
        align-content: center;
        gap: 6px;
        border: 1px dashed #aeb9cb;
        border-radius: 6px;
        background: #fbfcff;
        color: #64748b;
        cursor: pointer;
    }

    .upload-tile:hover {
        border-color: var(--lab-primary);
        color: var(--lab-primary);
        background: var(--lab-primary-soft);
    }

    .upload-tile span {
        display: block;
        max-width: 84px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        font-size: 12px;
        line-height: 1.3;
    }

    .el-icon-plus {
        font-style: normal;
        font-size: 28px;
        line-height: 1;
    }

    .lab-dialog {
        position: fixed;
        inset: 0;
        z-index: 1000;
        display: grid;
        place-items: center;
        background: rgba(15, 23, 42, 0.32);
        padding: 20px;
    }

    .el-dialog {
        width: min(760px, 100%);
        max-height: min(720px, 92vh);
        display: flex;
        flex-direction: column;
        background: #fff;
        border-radius: 8px;
        box-shadow: 0 24px 60px rgba(15, 23, 42, 0.22);
        overflow: hidden;
    }

    .el-dialog__header,
    .el-dialog__footer {
        padding: 14px 18px;
        border-bottom: 1px solid #edf1f7;
    }

    .el-dialog__footer {
        border-bottom: 0;
        border-top: 1px solid #edf1f7;
        text-align: right;
    }

    .el-dialog__title {
        font-size: 16px;
        font-weight: 700;
    }

    .el-dialog__body {
        padding: 16px 18px;
        overflow: auto;
    }

    .material-toolbar {
        display: flex;
        align-items: center;
        gap: 10px;
        margin-bottom: 12px;
    }

    .material-list {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(128px, 1fr));
        gap: 10px;
        min-height: 118px;
        padding: 10px;
        border: 1px dashed #d7deea;
        border-radius: 6px;
        background: #f8fafc;
    }

    .material-card {
        min-height: 88px;
        display: grid;
        align-content: center;
        gap: 8px;
        padding: 10px;
        border: 1px solid #d7deea;
        border-radius: 6px;
        background: #fff;
        cursor: pointer;
    }

    .material-card.is-selected {
        border-color: var(--lab-primary);
        box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }

    .material-thumb {
        height: 34px;
        border-radius: 4px;
        background: linear-gradient(135deg, #dbeafe, #f0fdf4);
    }

    .material-name {
        display: block;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        color: #334155;
        font-size: 13px;
        cursor: pointer;
    }

    .lab-empty {
        grid-column: 1 / -1;
        color: #94a3b8;
        font-size: 13px;
        align-self: center;
        justify-self: center;
    }

    .ql-wrap {
        border: 1px solid #cfd7e6;
        border-radius: 6px;
        overflow: hidden;
        background: #fff;
    }

    .ql-toolbar {
        display: flex;
        align-items: center;
        gap: 6px;
        min-height: 38px;
        padding: 6px 8px;
        border-bottom: 1px solid #edf1f7;
        background: #fbfcff;
    }

    .ql-image {
        width: 30px;
        height: 28px;
        border: 1px solid #d7deea;
        border-radius: 4px;
        background: #fff;
        cursor: pointer;
        position: relative;
    }

    .ql-image::before {
        content: "";
        position: absolute;
        left: 7px;
        top: 7px;
        width: 14px;
        height: 12px;
        border: 1px solid #64748b;
        border-radius: 2px;
    }

    .ql-image::after {
        content: "";
        position: absolute;
        left: 10px;
        top: 15px;
        width: 10px;
        height: 6px;
        background: linear-gradient(135deg, transparent 50%, #64748b 51%);
    }

    .ql-editor {
        min-height: 140px;
        padding: 12px;
        outline: none;
        line-height: 1.7;
    }

    .ql-editor:focus {
        box-shadow: inset 0 0 0 2px rgba(37, 99, 235, 0.12);
    }

    .ql-editor img {
        display: block;
        width: 92px;
        height: 56px;
        object-fit: cover;
        margin: 8px 0;
        border: 1px solid #d7deea;
        border-radius: 4px;
    }

    .lab-button {
        min-height: 36px;
        padding: 0 14px;
        border: 1px solid #cfd7e6;
        border-radius: 6px;
        background: #fff;
        color: #334155;
        font-size: 14px;
        cursor: pointer;
    }

    .lab-button:hover {
        border-color: #94a3b8;
        background: #f8fafc;
    }

    .lab-button.primary {
        border-color: var(--lab-primary);
        background: var(--lab-primary);
        color: #fff;
    }

    .lab-button.primary:hover {
        background: #1d4ed8;
    }

    .lab-actions {
        display: flex;
        justify-content: flex-end;
        gap: 10px;
        padding: 16px;
        border-top: 1px solid #edf1f7;
        background: #fbfcff;
    }

    .lab-result {
        position: sticky;
        top: 72px;
    }

    .lab-result pre {
        min-height: 260px;
        max-height: 520px;
        overflow: auto;
        padding: 12px;
        background: #0f172a;
        color: #dbeafe;
        border-radius: 0 0 8px 8px;
        font-size: 12px;
        line-height: 1.55;
        white-space: pre-wrap;
        word-break: break-word;
    }

    .lab-events {
        margin: 0;
        padding: 12px 12px 12px 30px;
        max-height: 220px;
        overflow: auto;
        color: #475569;
        font-size: 13px;
    }

    .lab-events li + li {
        margin-top: 6px;
    }

    .lab-pill {
        display: inline-flex;
        align-items: center;
        min-height: 26px;
        padding: 0 9px;
        border-radius: 999px;
        background: #e2e8f0;
        color: #334155;
        font-size: 12px;
    }

    @media (max-width: 980px) {
        .lab-shell {
            grid-template-columns: 1fr;
        }

        .lab-result {
            position: static;
        }
    }

    @media (max-width: 720px) {
        .lab-head {
            display: block;
        }

        .lab-head-actions {
            margin-top: 12px;
        }

        .lab-grid {
            grid-template-columns: 1fr;
        }

        .el-form-item {
            grid-template-columns: 1fr;
            gap: 4px;
        }

        .el-form-item__label {
            text-align: left;
            padding-top: 0;
        }
    }
</style>

<section class="control-lab" data-testid="control-lab">
    <div class="lab-head">
        <div>
            <h1>控件训练场</h1>
            <p>用于录制、生成经验、跑自动化脚本的小控件页面。</p>
        </div>
        <div class="lab-head-actions">
            <span class="lab-pill">Element / Avue 类名</span>
            <span class="lab-pill">含截图识别样本</span>
            <span class="lab-pill">可直接跑 Playwright</span>
        </div>
    </div>

    <div class="lab-shell">
        <div class="lab-panel">
            <div class="lab-panel-header">
                <h2>商品资料表单</h2>
                <span data-testid="lab-version">control-lab-v1</span>
            </div>

            <form id="controlLabForm" autocomplete="off">
                <div class="lab-section">
                    <h3>基础输入</h3>
                    <div class="lab-grid">
                        <div class="el-form-item is-required" data-field="product_name">
                            <label class="el-form-item__label" for="productName">商品名称</label>
                            <div class="el-form-item__content">
                                <div class="el-input">
                                    <input id="productName" name="product_name" class="el-input__inner" data-testid="product-name" placeholder="请输入商品名称，限100字">
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="sku_code">
                            <label class="el-form-item__label" for="skuCode">sku标识</label>
                            <div class="el-form-item__content">
                                <div class="el-input">
                                    <input id="skuCode" name="sku_code" class="el-input__inner" data-testid="sku-code" placeholder="请输入sku编码">
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="sale_price">
                            <label class="el-form-item__label" for="salePrice">销售价(元)</label>
                            <div class="el-form-item__content">
                                <div class="el-input el-input-number">
                                    <input id="salePrice" name="sale_price" class="el-input__inner" data-testid="sale-price" inputmode="decimal" placeholder="0.00">
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="cost_price">
                            <label class="el-form-item__label" for="costPrice">成本价(元)</label>
                            <div class="el-form-item__content">
                                <div class="el-input el-input-number">
                                    <input id="costPrice" name="cost_price" class="el-input__inner" data-testid="cost-price" inputmode="decimal" placeholder="0.00">
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="lab-section">
                    <h3>选择类控件</h3>
                    <div class="lab-grid">
                        <div class="el-form-item is-required" data-field="supplier">
                            <label class="el-form-item__label" for="supplierInput">供应商</label>
                            <div class="el-form-item__content">
                                <div class="el-select lab-select" data-select="supplier" data-testid="supplier-trigger">
                                    <div class="el-input el-input--suffix">
                                        <input id="supplierInput" class="el-input__inner" data-testid="supplier-input" placeholder="请选择 供应商" readonly>
                                        <span class="el-input__suffix">⌄</span>
                                    </div>
                                </div>
                                <div class="el-select-dropdown el-popper lab-dropdown" data-testid="supplier-dropdown" hidden>
                                    <ul class="el-select-dropdown__list" role="listbox">
                                        <li class="el-select-dropdown__item" role="option" data-value="西安庄信新材料科技有限公司" data-testid="supplier-option-1"><span>西安庄信新材料科技有限公司</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="西安稻叶山供应链管理有限公司" data-testid="supplier-option-2"><span>西安稻叶山供应链管理有限公司</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="河北白石商贸有限公司" data-testid="supplier-option-3"><span>河北白石商贸有限公司</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="陕西云仓供应链有限公司" data-testid="supplier-option-4"><span>陕西云仓供应链有限公司</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="西安稻叶山供应链管理有限公司-备用仓" data-testid="supplier-option-5"><span>西安稻叶山供应链管理有限公司-备用仓</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="超长名称测试供应商有限公司第一分公司西北运营中心" data-testid="supplier-option-6"><span>超长名称测试供应商有限公司第一分公司西北运营中心</span></li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item is-required" data-field="brand">
                            <label class="el-form-item__label" for="brandInput">品牌</label>
                            <div class="el-form-item__content">
                                <div class="el-select avue-select lab-select is-filterable" data-select="brand" data-testid="brand-trigger">
                                    <div class="el-input el-input--suffix">
                                        <input id="brandInput" class="el-input__inner" data-testid="brand-input" placeholder="请选择 品牌">
                                        <span class="el-input__suffix">⌄</span>
                                    </div>
                                </div>
                                <div class="el-select-dropdown avue-select-dropdown el-popper lab-dropdown" data-testid="brand-dropdown" hidden>
                                    <ul class="el-select-dropdown__list" role="listbox">
                                        <li class="el-select-dropdown__item lab-zero-placeholder" role="option" data-value="蓝月亮占位">蓝月亮</li>
                                        <li class="el-select-dropdown__item" role="option" data-value="蓝月亮" data-search="蓝 蓝月亮 lanyueliang" data-testid="brand-option-blue"><span>蓝月亮</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="蓝月亮旗舰店" data-search="蓝 蓝月亮 旗舰 店 lanyueliang qijian" data-testid="brand-option-blue-shop"><span>蓝月亮旗舰店</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="蓝月亮洗衣液" data-search="蓝 蓝月亮 洗衣液 lanyueliang xiyiye" data-testid="brand-option-blue-wash"><span>蓝月亮洗衣液</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="立白" data-search="立 立白 libai" data-testid="brand-option-libai"><span>立白</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="得力" data-search="得 得力 deli" data-testid="brand-option-deli"><span>得力</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="晨光" data-search="晨 晨光 m&g chenguang" data-testid="brand-option-mg"><span>晨光</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="清风" data-search="清 清风 qingfeng" data-testid="brand-option-qingfeng"><span>清风</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="心相印" data-search="心 心相印 xinxiangyin" data-testid="brand-option-xxy"><span>心相印</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="海尔" data-search="海 海尔 haier" data-testid="brand-option-haier"><span>海尔</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="美的" data-search="美 美的 midea" data-testid="brand-option-midea"><span>美的</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="小米" data-search="小 小米 mi xiaomi" data-testid="brand-option-xiaomi"><span>小米</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="公牛" data-search="公 公牛 bull gongniu" data-testid="brand-option-bull"><span>公牛</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-value="京东京造" data-search="京 京东京造 jd jingzao" data-testid="brand-option-jd"><span>京东京造</span></li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item is-required" data-field="category">
                            <label class="el-form-item__label" for="categoryInput">商品类目</label>
                            <div class="el-form-item__content">
                                <div class="el-cascader lab-cascader" data-testid="category-trigger">
                                    <div class="el-input el-input--suffix">
                                        <input id="categoryInput" class="el-input__inner" data-testid="category-input" placeholder="请选择 商品类目" readonly>
                                        <span class="el-input__suffix">⌄</span>
                                    </div>
                                </div>
                                <div class="el-cascader-panel el-popper lab-cascader-panel" data-testid="category-panel" hidden>
                                    <div class="el-cascader-menu" data-testid="category-level-1">
                                        <ul class="el-cascader-menu__list" role="menu">
                                            <li id="cascader-menu-lab-0-0" class="el-cascader-node" role="menuitem" data-value="办公电器" data-testid="category-office-electric"><span>办公电器</span></li>
                                            <li id="cascader-menu-lab-0-1" class="el-cascader-node" role="menuitem" data-value="办公耗材" data-testid="category-office-supply"><span>办公耗材</span></li>
                                            <li id="cascader-menu-lab-0-2" class="el-cascader-node" role="menuitem" data-value="办公家具" data-testid="category-office-furniture"><span>办公家具</span></li>
                                            <li id="cascader-menu-lab-0-3" class="el-cascader-node" role="menuitem" data-value="办公日常" data-testid="category-office-daily"><span>办公日常</span></li>
                                            <li id="cascader-menu-lab-0-4" class="el-cascader-node" role="menuitem" data-value="清洁个护" data-testid="category-clean-personal"><span>清洁个护</span></li>
                                            <li id="cascader-menu-lab-0-5" class="el-cascader-node" role="menuitem" data-value="食品饮料" data-testid="category-food-drink"><span>食品饮料</span></li>
                                        </ul>
                                    </div>
                                    <div class="el-cascader-menu" data-testid="category-level-2">
                                        <ul class="el-cascader-menu__list" role="menu">
                                            <li id="cascader-menu-lab-1-0" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="清洁用品" data-testid="category-cleaning"><span>清洁用品</span></li>
                                            <li id="cascader-menu-lab-1-1" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="日用杂品" data-testid="category-daily-goods"><span>日用杂品</span></li>
                                            <li id="cascader-menu-lab-1-2" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="劳保用品" data-testid="category-labor"><span>劳保用品</span></li>
                                            <li id="cascader-menu-lab-1-3" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="办公纸品" data-testid="category-paper"><span>办公纸品</span></li>
                                            <li id="cascader-menu-lab-1-4" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="文件收纳" data-testid="category-storage"><span>文件收纳</span></li>
                                            <li id="cascader-menu-lab-1-5" class="el-cascader-node" role="menuitem" data-parent="办公日常" data-value="会议用品" data-testid="category-meeting"><span>会议用品</span></li>
                                        </ul>
                                    </div>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="product_type">
                            <label class="el-form-item__label" for="asyncSearch">商品类型</label>
                            <div class="el-form-item__content">
                                <div class="el-select lab-select" data-select="async-product-type" data-testid="async-type-trigger">
                                    <div class="el-input el-input--suffix">
                                        <input id="asyncSearch" class="el-input__inner" data-testid="async-search" placeholder="输入后异步加载">
                                        <span class="el-input__suffix">⌄</span>
                                    </div>
                                </div>
                                <div class="el-select-dropdown el-popper lab-dropdown" data-testid="async-dropdown" hidden>
                                    <ul class="el-select-dropdown__list" role="listbox">
                                        <li class="el-select-dropdown__item" data-loading="1"><span>加载中...</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="普通商品" data-search="普通 商品" data-testid="async-option-normal" hidden><span>普通商品</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="服务商品" data-search="服务 商品" data-testid="async-option-service" hidden><span>服务商品</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="虚拟商品" data-search="虚拟 商品 卡券" data-testid="async-option-virtual" hidden><span>虚拟商品</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="组合商品" data-search="组合 套装 商品" data-testid="async-option-combo" hidden><span>组合商品</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="预售商品" data-search="预售 预约 商品" data-testid="async-option-presale" hidden><span>预售商品</span></li>
                                        <li class="el-select-dropdown__item" role="option" data-delay-option="1" data-value="积分商品" data-search="积分 商品 兑换" data-testid="async-option-points" hidden><span>积分商品</span></li>
                                    </ul>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="delivery_template">
                            <label class="el-form-item__label" for="deliverySelect">运费模板</label>
                            <div class="el-form-item__content">
                                <select id="deliverySelect" class="lab-native-select" data-testid="delivery-select">
                                    <option value="">请选择 运费模板</option>
                                    <option value="集采不含运">集采不含运</option>
                                    <option value="全国包邮">全国包邮</option>
                                    <option value="同城配送">同城配送</option>
                                    <option value="到付">到付</option>
                                    <option value="大件物流">大件物流</option>
                                    <option value="冷链配送">冷链配送</option>
                                    <option value="供应商承担运费">供应商承担运费</option>
                                    <option value="买家承担运费">买家承担运费</option>
                                </select>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="publish_status">
                            <label class="el-form-item__label">是否上架</label>
                            <div class="el-form-item__content">
                                <div class="lab-inline-options">
                                    <label class="el-radio" data-testid="status-off"><input type="radio" name="publish_status" value="下架">下架</label>
                                    <label class="el-radio" data-testid="status-on"><input type="radio" name="publish_status" value="上架">上架</label>
                                    <label class="el-checkbox" data-testid="support-group-buy"><input type="checkbox" name="support_group_buy" value="1">支持集采</label>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="lab-section">
                    <h3>多级菜单与标签页</h3>
                    <div class="lab-menu-board">
                        <ul class="el-menu" data-testid="multi-menu">
                            <li class="el-submenu" data-testid="menu-goods">
                                <div class="el-submenu__title">商品管理 <span>›</span></div>
                                <ul class="el-menu" hidden>
                                    <li class="el-submenu" data-testid="menu-goods-base">
                                        <div class="el-submenu__title">商品资料 <span>›</span></div>
                                        <ul class="el-menu" hidden>
                                            <li class="el-menu-item" data-menu-path="商品管理/商品资料/新增商品" data-testid="menu-add-goods">新增商品</li>
                                            <li class="el-menu-item" data-menu-path="商品管理/商品资料/商品列表" data-testid="menu-goods-list">商品列表</li>
                                        </ul>
                                    </li>
                                    <li class="el-submenu" data-testid="menu-material">
                                        <div class="el-submenu__title">素材中心 <span>›</span></div>
                                        <ul class="el-menu" hidden>
                                            <li class="el-menu-item" data-menu-path="商品管理/素材中心/网络图库" data-testid="menu-network-gallery">网络图库</li>
                                            <li class="el-menu-item" data-menu-path="商品管理/素材中心/历史图片" data-testid="menu-history-images">历史图片</li>
                                        </ul>
                                    </li>
                                </ul>
                            </li>
                            <li class="el-submenu" data-testid="menu-order">
                                <div class="el-submenu__title">订单管理 <span>›</span></div>
                                <ul class="el-menu" hidden>
                                    <li class="el-menu-item" data-menu-path="订单管理/待发货" data-testid="menu-order-wait">待发货</li>
                                    <li class="el-menu-item" data-menu-path="订单管理/已完成" data-testid="menu-order-done">已完成</li>
                                </ul>
                            </li>
                        </ul>

                        <div class="lab-tabs" data-testid="tabs-box">
                            <div class="el-tabs__header">
                                <button type="button" class="el-tabs__item is-active" data-tab="base" data-testid="tab-base">基础信息</button>
                                <button type="button" class="el-tabs__item" data-tab="price" data-testid="tab-price">价格库存</button>
                                <button type="button" class="el-tabs__item" data-tab="image" data-testid="tab-image">图片描述</button>
                            </div>
                            <div class="el-tab-pane" data-pane="base" data-testid="pane-base">当前页签：基础信息。适合测试 tab 切换后再填写字段。</div>
                            <div class="el-tab-pane" data-pane="price" data-testid="pane-price" hidden>当前页签：价格库存。适合测试隐藏区域变可见后的输入。</div>
                            <div class="el-tab-pane" data-pane="image" data-testid="pane-image" hidden>当前页签：图片描述。适合测试切换到图片区后上传。</div>
                        </div>
                    </div>
                </div>

                <div class="lab-section">
                    <h3>图片与素材库</h3>
                    <div class="lab-grid">
                        <div class="el-form-item is-required" data-field="main_images">
                            <label class="el-form-item__label">商品图片</label>
                            <div class="el-form-item__content">
                                <div class="upload-tile" data-testid="main-image-open" title="打开商品图片素材库">
                                    <i class="el-icon-plus">+</i>
                                    <span>本地上传</span>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="network_images">
                            <label class="el-form-item__label">网络图库</label>
                            <div class="el-form-item__content">
                                <div class="upload-tile" data-testid="network-gallery-open" title="打开网络图库">
                                    <i class="el-icon-plus">+</i>
                                    <span>图库选图</span>
                                </div>
                            </div>
                        </div>

                        <div class="el-form-item" data-field="sale_date">
                            <label class="el-form-item__label" for="saleDateInput">上架日期</label>
                            <div class="el-form-item__content">
                                <div class="el-date-editor el-input lab-date" data-testid="date-trigger">
                                    <input id="saleDateInput" class="el-input__inner" data-testid="sale-date" placeholder="请选择日期" readonly>
                                </div>
                                <div class="el-picker-panel el-popper lab-date-panel" data-testid="date-panel" hidden>
                                    <ul class="el-select-dropdown__list" role="listbox">
                                        <li class="el-select-dropdown__item" role="option" data-date="2026-05-28" data-testid="date-today">2026-05-28</li>
                                        <li class="el-select-dropdown__item" role="option" data-date="2026-05-29" data-testid="date-tomorrow">2026-05-29</li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="lab-section">
                    <h3>富文本描述</h3>
                    <div class="lab-grid full">
                        <div class="el-form-item" data-field="description">
                            <label class="el-form-item__label">描述</label>
                            <div class="el-form-item__content">
                                <div class="ql-wrap">
                                    <div class="ql-toolbar">
                                        <button type="button" class="ql-image" data-testid="editor-image-button" title="图片"></button>
                                    </div>
                                    <div class="ql-editor" contenteditable="true" data-testid="editor" data-images="[]"></div>
                                    <input type="file" data-testid="detail-image-file" accept="image/*" multiple hidden>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="lab-actions">
                    <button type="button" class="lab-button" data-testid="reset-lab">重 置</button>
                    <button type="button" class="lab-button primary" data-testid="save-lab">保 存</button>
                </div>
            </form>
        </div>

        <aside class="lab-panel lab-result">
            <div class="lab-panel-header">
                <h2>操作结果</h2>
                <span>JSON</span>
            </div>
            <pre id="labState" data-testid="lab-state">{}</pre>
            <div class="lab-panel-header">
                <h2>事件记录</h2>
                <span>最近 20 条</span>
            </div>
            <ol id="labEvents" class="lab-events" data-testid="lab-events"></ol>
        </aside>
    </div>
</section>

<div class="el-dialog__wrapper lab-dialog" data-testid="main-image-dialog" hidden>
    <div class="el-dialog" role="dialog" aria-modal="true" aria-label="商品图片素材库">
        <div class="el-dialog__header">
            <span class="el-dialog__title">商品图片素材库</span>
        </div>
        <div class="el-dialog__body">
            <div class="material-toolbar">
                <button type="button" class="lab-button primary" data-testid="main-upload-button">点击上传</button>
                <span class="lab-pill" data-testid="main-upload-count">已上传 0 张</span>
            </div>
            <input type="file" data-testid="main-image-file" accept="image/*" multiple hidden>
            <div class="material-list" data-testid="main-material-list">
                <span class="lab-empty">等待上传图片</span>
            </div>
        </div>
        <div class="el-dialog__footer">
            <button type="button" class="lab-button" data-testid="main-image-cancel">取 消</button>
            <button type="button" class="lab-button primary" data-testid="main-image-confirm">确 定</button>
        </div>
    </div>
</div>

<div class="el-dialog__wrapper lab-dialog" data-testid="network-gallery-dialog" hidden>
    <div class="el-dialog" role="dialog" aria-modal="true" aria-label="网络图库">
        <div class="el-dialog__header">
            <span class="el-dialog__title">网络图库</span>
        </div>
        <div class="el-dialog__body">
            <div class="material-toolbar">
                <div class="el-input" style="max-width: 260px">
                    <input class="el-input__inner" data-testid="network-gallery-search" placeholder="搜索图片名称，如 蓝月亮">
                </div>
                <button type="button" class="lab-button" data-testid="network-gallery-search-btn">搜 索</button>
                <span class="lab-pill" data-testid="network-selected-count">已选择 0 张</span>
            </div>
            <div class="material-list" data-testid="network-material-list">
                <div class="material-card" data-network-name="blue-main-01.jpg" data-search="蓝月亮 主图 blue" data-testid="network-card-blue-main">
                    <div class="material-thumb"></div>
                    <label class="material-name">blue-main-01.jpg</label>
                </div>
                <div class="material-card" data-network-name="blue-detail-02.jpg" data-search="蓝月亮 详情 detail" data-testid="network-card-blue-detail">
                    <div class="material-thumb"></div>
                    <label class="material-name">blue-detail-02.jpg</label>
                </div>
                <div class="material-card" data-network-name="last-used-main.jpg" data-search="上次 历史 图片 last" data-testid="network-card-last-main">
                    <div class="material-thumb"></div>
                    <label class="material-name">last-used-main.jpg</label>
                </div>
                <div class="material-card" data-network-name="office-cleaning.png" data-search="办公 清洁 图片 office" data-testid="network-card-office-clean">
                    <div class="material-thumb"></div>
                    <label class="material-name">office-cleaning.png</label>
                </div>
            </div>
        </div>
        <div class="el-dialog__footer">
            <button type="button" class="lab-button" data-testid="network-gallery-cancel">取 消</button>
            <button type="button" class="lab-button primary" data-testid="network-gallery-confirm">确 定</button>
        </div>
    </div>
</div>

<script>
(() => {
    const $ = (selector, root = document) => root.querySelector(selector);
    const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));
    const state = {
        supplier: "",
        brand: "",
        category: [],
        productType: "",
        menuPath: "",
        activeTab: "base",
        mainImages: [],
        selectedMainImages: [],
        networkImages: [],
        detailImages: [],
        saleDate: ""
    };
    let asyncLoaded = false;

    function log(message) {
        const list = $("#labEvents");
        const item = document.createElement("li");
        item.textContent = `${new Date().toLocaleTimeString()} ${message}`;
        list.prepend(item);
        while (list.children.length > 20) {
            list.lastElementChild.remove();
        }
    }

    function renderState() {
        const payload = {
            product_name: $("#productName").value,
            sku_code: $("#skuCode").value,
            sale_price: $("#salePrice").value,
            cost_price: $("#costPrice").value,
            supplier: state.supplier,
            brand: state.brand || $("#brandInput").value,
            category: state.category,
            product_type: state.productType || $("#asyncSearch").value,
            menu_path: state.menuPath,
            active_tab: state.activeTab,
            delivery_template: $("#deliverySelect").value,
            publish_status: ($("input[name='publish_status']:checked") || {}).value || "",
            support_group_buy: $("input[name='support_group_buy']").checked,
            sale_date: state.saleDate || $("#saleDateInput").value,
            main_images: state.mainImages,
            selected_main_images: state.selectedMainImages,
            network_images: state.networkImages,
            detail_images: state.detailImages,
            description_text: $("[data-testid='editor']").innerText.trim()
        };
        window.controlLabState = payload;
        $("#labState").textContent = JSON.stringify(payload, null, 2);
        return payload;
    }

    function closeFloaters(except) {
        $$(".lab-dropdown, .lab-cascader-panel, .lab-date-panel").forEach((panel) => {
            if (panel !== except) {
                panel.hidden = true;
            }
        });
    }

    function openPanel(panel) {
        closeFloaters(panel);
        panel.hidden = false;
    }

    function selectOption(input, option, key) {
        const value = option.dataset.value || option.dataset.date || option.textContent.trim();
        input.value = value;
        if (key) {
            state[key] = value;
        }
        option.closest(".lab-dropdown, .lab-date-panel").hidden = true;
        $$("[role='option']", option.parentElement).forEach((item) => item.classList.remove("is-selected"));
        option.classList.add("is-selected");
        log(`选择 ${value}`);
        renderState();
    }

    $("[data-testid='supplier-trigger']").addEventListener("click", () => {
        openPanel($("[data-testid='supplier-dropdown']"));
        log("打开供应商下拉");
    });

    $$("[data-testid='supplier-dropdown'] [role='option']").forEach((option) => {
        option.addEventListener("click", () => selectOption($("#supplierInput"), option, "supplier"));
    });

    const brandInput = $("#brandInput");
    const brandDropdown = $("[data-testid='brand-dropdown']");
    $("[data-testid='brand-trigger']").addEventListener("click", () => {
        openPanel(brandDropdown);
        brandInput.focus();
        log("打开品牌搜索下拉");
    });
    brandInput.addEventListener("input", () => {
        openPanel(brandDropdown);
        const keyword = brandInput.value.trim().toLowerCase();
        $$("[data-testid='brand-dropdown'] [role='option']").forEach((option) => {
            if (option.classList.contains("lab-zero-placeholder")) {
                return;
            }
            const haystack = `${option.dataset.search || ""} ${option.textContent}`.toLowerCase();
            option.hidden = Boolean(keyword) && !haystack.includes(keyword);
        });
    });
    $$("[data-testid='brand-dropdown'] [role='option']").forEach((option) => {
        if (option.classList.contains("lab-zero-placeholder")) {
            return;
        }
        option.addEventListener("click", () => selectOption(brandInput, option, "brand"));
    });

    const asyncInput = $("#asyncSearch");
    const asyncDropdown = $("[data-testid='async-dropdown']");
    function loadAsyncOptions() {
        openPanel(asyncDropdown);
        if (asyncLoaded) {
            return;
        }
        asyncLoaded = true;
        setTimeout(() => {
            $("[data-loading='1']", asyncDropdown).hidden = true;
            $$("[data-delay-option='1']", asyncDropdown).forEach((item) => item.hidden = false);
            log("异步选项加载完成");
        }, 700);
    }
    $("[data-testid='async-type-trigger']").addEventListener("click", loadAsyncOptions);
    asyncInput.addEventListener("input", () => {
        loadAsyncOptions();
        const keyword = asyncInput.value.trim();
        $$("[data-delay-option='1']", asyncDropdown).forEach((option) => {
            const haystack = `${option.dataset.search || ""} ${option.textContent}`;
            option.hidden = keyword ? !haystack.includes(keyword) : false;
        });
    });
    $$("[data-delay-option='1']", asyncDropdown).forEach((option) => {
        option.addEventListener("click", () => selectOption(asyncInput, option, "productType"));
    });

    const categoryInput = $("#categoryInput");
    const categoryPanel = $("[data-testid='category-panel']");
    let categoryFirst = "";
    $("[data-testid='category-trigger']").addEventListener("click", () => {
        openPanel(categoryPanel);
        log("打开商品类目级联");
    });
    $$("[data-testid='category-level-1'] .el-cascader-node").forEach((node) => {
        node.addEventListener("click", () => {
            categoryFirst = node.dataset.value;
            $$("[data-testid='category-level-1'] .el-cascader-node").forEach((item) => item.classList.remove("in-active-path"));
            node.classList.add("in-active-path");
            state.category = [categoryFirst];
            categoryInput.value = categoryFirst;
            log(`选择一级类目 ${categoryFirst}`);
            renderState();
        });
    });
    $$("[data-testid='category-level-2'] .el-cascader-node").forEach((node) => {
        node.addEventListener("click", () => {
            if (!categoryFirst) {
                categoryFirst = "办公日常";
            }
            const second = node.dataset.value;
            state.category = [categoryFirst, second];
            categoryInput.value = `${categoryFirst} / ${second}`;
            $$("[data-testid='category-level-2'] .el-cascader-node").forEach((item) => item.classList.remove("is-selected"));
            node.classList.add("is-selected");
            categoryPanel.hidden = true;
            log(`选择二级类目 ${second}`);
            renderState();
        });
    });

    $$(".el-submenu__title").forEach((title) => {
        title.addEventListener("click", (event) => {
            event.stopPropagation();
            const submenu = title.parentElement;
            const childMenu = submenu.querySelector(":scope > .el-menu");
            if (childMenu) {
                childMenu.hidden = !childMenu.hidden;
                log(`展开菜单 ${title.textContent.trim()}`);
            }
        });
    });
    $$(".el-menu-item[data-menu-path]").forEach((item) => {
        item.addEventListener("click", (event) => {
            event.stopPropagation();
            $$(".el-menu-item[data-menu-path]").forEach((node) => node.classList.remove("is-active"));
            item.classList.add("is-active");
            state.menuPath = item.dataset.menuPath;
            log(`选择菜单 ${state.menuPath}`);
            renderState();
        });
    });

    $$(".el-tabs__item[data-tab]").forEach((tab) => {
        tab.addEventListener("click", () => {
            const name = tab.dataset.tab;
            $$(".el-tabs__item[data-tab]").forEach((item) => item.classList.toggle("is-active", item === tab));
            $$("[data-pane]").forEach((pane) => {
                pane.hidden = pane.dataset.pane !== name;
            });
            state.activeTab = name;
            log(`切换页签 ${tab.textContent.trim()}`);
            renderState();
        });
    });

    const dateInput = $("#saleDateInput");
    const datePanel = $("[data-testid='date-panel']");
    $("[data-testid='date-trigger']").addEventListener("click", () => {
        openPanel(datePanel);
        log("打开日期面板");
    });
    $$("[data-date]").forEach((option) => {
        option.addEventListener("click", () => selectOption(dateInput, option, "saleDate"));
    });

    $("[data-testid='main-image-open']").addEventListener("click", () => {
        $("[data-testid='main-image-dialog']").hidden = false;
        log("打开商品图片素材库");
    });
    $("[data-testid='main-image-cancel']").addEventListener("click", () => {
        $("[data-testid='main-image-dialog']").hidden = true;
    });
    $("[data-testid='main-upload-button']").addEventListener("click", () => {
        $("[data-testid='main-image-file']").click();
    });
    $("[data-testid='main-image-file']").addEventListener("change", (event) => {
        const files = Array.from(event.target.files || []);
        state.mainImages = files.map((file) => file.name);
        state.selectedMainImages = [];
        const list = $("[data-testid='main-material-list']");
        list.innerHTML = "";
        if (!files.length) {
            list.innerHTML = '<span class="lab-empty">等待上传图片</span>';
        }
        files.forEach((file) => {
            const card = document.createElement("div");
            card.className = "material-card";
            card.dataset.fileName = file.name;
            const thumb = document.createElement("div");
            thumb.className = "material-thumb";
            const label = document.createElement("label");
            label.className = "material-name";
            label.textContent = file.name;
            label.dataset.fileName = file.name;
            label.tabIndex = 0;
            card.appendChild(thumb);
            card.appendChild(label);
            card.addEventListener("click", () => {
                card.classList.toggle("is-selected");
                state.selectedMainImages = $$(".material-card.is-selected", list).map((item) => item.dataset.fileName);
                log(`切换商品图片 ${file.name}`);
                renderState();
            });
            list.appendChild(card);
        });
        $("[data-testid='main-upload-count']").textContent = `已上传 ${files.length} 张`;
        log(`上传商品图片 ${files.length} 张`);
        renderState();
    });
    $("[data-testid='main-image-confirm']").addEventListener("click", () => {
        const list = $("[data-testid='main-material-list']");
        state.selectedMainImages = $$(".material-card.is-selected", list).map((item) => item.dataset.fileName);
        if (!state.selectedMainImages.length) {
            state.selectedMainImages = state.mainImages.slice();
            $$(".material-card", list).forEach((item) => item.classList.add("is-selected"));
        }
        $("[data-testid='main-image-dialog']").hidden = true;
        log(`确认商品图片 ${state.selectedMainImages.length} 张`);
        renderState();
    });

    function updateNetworkSelectedCount() {
        const selected = $$(".material-card.is-selected", $("[data-testid='network-material-list']")).map((card) => card.dataset.networkName);
        $("[data-testid='network-selected-count']").textContent = `已选择 ${selected.length} 张`;
        return selected;
    }

    $("[data-testid='network-gallery-open']").addEventListener("click", () => {
        $("[data-testid='network-gallery-dialog']").hidden = false;
        log("打开网络图库");
    });
    $("[data-testid='network-gallery-cancel']").addEventListener("click", () => {
        $("[data-testid='network-gallery-dialog']").hidden = true;
    });
    $("[data-testid='network-material-list']").addEventListener("click", (event) => {
        const card = event.target.closest(".material-card");
        if (!card) {
            return;
        }
        card.classList.toggle("is-selected");
        updateNetworkSelectedCount();
        log(`切换网络图库图片 ${card.dataset.networkName}`);
    });
    function filterNetworkGallery() {
        const keyword = $("[data-testid='network-gallery-search']").value.trim().toLowerCase();
        $$(".material-card", $("[data-testid='network-material-list']")).forEach((card) => {
            const haystack = `${card.dataset.search || ""} ${card.dataset.networkName || ""}`.toLowerCase();
            card.hidden = Boolean(keyword) && !haystack.includes(keyword);
        });
        log(`搜索网络图库 ${keyword || "全部"}`);
    }
    $("[data-testid='network-gallery-search-btn']").addEventListener("click", filterNetworkGallery);
    $("[data-testid='network-gallery-search']").addEventListener("input", filterNetworkGallery);
    $("[data-testid='network-gallery-confirm']").addEventListener("click", () => {
        state.networkImages = updateNetworkSelectedCount();
        $("[data-testid='network-gallery-dialog']").hidden = true;
        log(`确认网络图库 ${state.networkImages.length} 张`);
        renderState();
    });

    const detailInput = $("[data-testid='detail-image-file']");
    const editor = $("[data-testid='editor']");
    $("[data-testid='editor-image-button']").addEventListener("click", () => {
        detailInput.click();
    });
    detailInput.addEventListener("change", (event) => {
        const files = Array.from(event.target.files || []);
        const current = JSON.parse(editor.dataset.images || "[]");
        files.forEach((file) => {
            current.push(file.name);
            const img = document.createElement("img");
            img.alt = file.name;
            img.dataset.fileName = file.name;
            img.src = URL.createObjectURL(file);
            editor.appendChild(img);
        });
        editor.dataset.images = JSON.stringify(current);
        state.detailImages = current;
        log(`插入详情图 ${files.length} 张`);
        renderState();
    });

    ["input", "change"].forEach((eventName) => {
        $("#controlLabForm").addEventListener(eventName, renderState);
    });

    $("[data-testid='save-lab']").addEventListener("click", () => {
        renderState();
        log("保存表单");
    });

    $("[data-testid='reset-lab']").addEventListener("click", () => {
        $("#controlLabForm").reset();
        Object.assign(state, {
            supplier: "",
            brand: "",
            category: [],
            productType: "",
            menuPath: "",
            activeTab: "base",
            mainImages: [],
            selectedMainImages: [],
            networkImages: [],
            detailImages: [],
            saleDate: ""
        });
        $("#supplierInput").value = "";
        $("#brandInput").value = "";
        $("#categoryInput").value = "";
        $("#asyncSearch").value = "";
        $("#saleDateInput").value = "";
        editor.innerHTML = "";
        editor.dataset.images = "[]";
        $("[data-testid='main-material-list']").innerHTML = '<span class="lab-empty">等待上传图片</span>';
        $("[data-testid='main-upload-count']").textContent = "已上传 0 张";
        $$(".material-card", $("[data-testid='network-material-list']")).forEach((card) => {
            card.classList.remove("is-selected");
            card.hidden = false;
        });
        $("[data-testid='network-gallery-search']").value = "";
        $("[data-testid='network-selected-count']").textContent = "已选择 0 张";
        $$(".el-menu-item[data-menu-path]").forEach((item) => item.classList.remove("is-active"));
        $$(".el-submenu > .el-menu").forEach((menu) => menu.hidden = true);
        $$(".el-tabs__item[data-tab]").forEach((tab) => tab.classList.toggle("is-active", tab.dataset.tab === "base"));
        $$("[data-pane]").forEach((pane) => pane.hidden = pane.dataset.pane !== "base");
        log("重置表单");
        renderState();
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".el-form-item__content")) {
            closeFloaters();
        }
    });

    renderState();
})();
</script>
@endsection
