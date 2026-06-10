<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>免费训练场 | 网页自动化工作室</title>
  <link rel="stylesheet" href="/assets/styles.css">
</head>
<body>
  <header class="topbar">
    <nav class="nav">
      <a class="brand" href="/"><span class="mark">AI</span><span>网页自动化工作室</span></a>
      <div class="links">
        <a href="/">首页</a>
        <a href="/console.php">用户中心</a>
      </div>
    </nav>
  </header>

  <main class="container two">
    <aside class="panel sticky">
      <div class="eyebrow">免费训练场</div>
      <h2>模拟商品发布后台</h2>
      <p>用桌面软件打开本页，按表单操作并登记业务动作。这里免费，用来练习和检测软件能力。</p>
      <p>建议登记动作：填写商品名称、选择分类、选择品牌、填写价格、上传主图、勾选确认、保存商品。</p>
    </aside>

    <section class="panel">
      <h1 style="font-size:32px">发布测试商品</h1>
      <p>图片会在浏览器端压缩，不要上传隐私图片。</p>
      <form id="trainingForm" class="form-grid">
        <label>商品名称
          <input id="productName" name="product_name" placeholder="例如：训练场测试商品" data-train-field="商品名称">
        </label>
        <label>商品分类
          <select id="category" name="category" data-train-field="商品分类">
            <option value="">请选择分类</option>
            <option value="食品饮料/休闲零食">食品饮料 / 休闲零食</option>
            <option value="家居百货/收纳清洁">家居百货 / 收纳清洁</option>
            <option value="数码配件/手机配件">数码配件 / 手机配件</option>
          </select>
        </label>
        <label>品牌
          <input id="brand" name="brand" list="brandList" placeholder="输入或选择品牌" data-train-field="品牌">
          <datalist id="brandList">
            <option value="自有品牌"></option>
            <option value="训练品牌A"></option>
            <option value="训练品牌B"></option>
          </datalist>
        </label>
        <label>销售价
          <input id="price" name="price" type="number" min="0" step="0.01" placeholder="例如：19.90" data-train-field="销售价">
        </label>
        <label class="full">商品详情
          <textarea id="detail" name="detail" placeholder="写一段商品说明，用来练习多行文本输入。" data-train-field="商品详情"></textarea>
        </label>
        <div class="full upload">
          <label>主图上传
            <input id="imageInput" name="image" type="file" accept="image/*" data-train-field="主图">
          </label>
          <div class="preview">
            <img id="previewImage" hidden alt="图片预览">
            <span id="imageInfo">选择图片后会压缩到 400x400 左右，尽量接近 50KB。</span>
          </div>
        </div>
        <div class="full inline">
          <input id="agree" name="agree" type="checkbox" value="yes">
          <label for="agree" style="display:inline;margin:0">我确认这是训练数据，不包含隐私内容</label>
        </div>
        <div class="full actions">
          <button type="submit">保存测试商品</button>
          <button type="button" class="secondary" id="fillDemo">填入示例数据</button>
          <button type="reset" class="ghost">清空</button>
        </div>
      </form>
      <div id="trainingStatus" class="status" hidden></div>
    </section>
  </main>

  <script src="/assets/app.js"></script>
  <script>
    let compressedImage = null;
    let compressedName = "training-image.jpg";

    $("#fillDemo").addEventListener("click", () => {
      $("#productName").value = "训练场测试商品";
      $("#category").value = "食品饮料/休闲零食";
      $("#brand").value = "训练品牌A";
      $("#price").value = "19.90";
      $("#detail").value = "这是一条用于网页自动化训练的商品详情。";
      $("#agree").checked = true;
    });

    $("#imageInput").addEventListener("change", async (event) => {
      const file = event.target.files[0];
      if (!file) return;
      compressedImage = await compressImage(file);
      compressedName = file.name.replace(/\.[^.]+$/, "") + "-compressed.jpg";
      $("#previewImage").src = URL.createObjectURL(compressedImage);
      $("#previewImage").hidden = false;
      $("#imageInfo").textContent = `已压缩：${Math.round(compressedImage.size / 1024)}KB，文件名：${compressedName}`;
    });

    $("#trainingForm").addEventListener("submit", async (event) => {
      event.preventDefault();
      try {
        if (!$("#agree").checked) throw new Error("请先勾选训练数据确认。");
        const form = new FormData(event.target);
        if (compressedImage) form.set("image", compressedImage, compressedName);
        const data = await Api.call("training.submit", { method: "POST", body: form });
        statusBox("#trainingStatus", `提交成功，训练编号：${data.id}，图片大小：${Math.round((data.image_size || 0) / 1024)}KB。`);
      } catch (err) {
        statusBox("#trainingStatus", err.message, true);
      }
    });
  </script>
</body>
</html>
