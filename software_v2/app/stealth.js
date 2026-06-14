/*
 * 防自动化检测补丁 — 抹掉 Playwright / Selenium 的特征指纹
 * ========================================================
 * 注入到 page.add_init_script，每个新 document 创建时立即运行
 *
 * 攻防点参考：https://bot.sannysoft.com 等检测页能直观看效果
 *
 * 注意：
 * - 仅用于配合用户真实 Edge 浏览器（通过 CDP 附加），不是给 Playwright 自带 Chromium 用
 * - 即便如此 CDP 协议本身也有少量痕迹，但聚水潭这级别的反爬一般够用
 */

(() => {
    if (window.__hbf_stealth_applied) return;
    window.__hbf_stealth_applied = true;

    // ─── 1. 隐藏 navigator.webdriver ───
    // 自动化浏览器中 navigator.webdriver === true（最常见检测点）
    try {
        Object.defineProperty(navigator, "webdriver", {
            get: () => undefined,
            configurable: true,
        });
    } catch (e) {}

    // ─── 2. 修复 navigator.languages ───
    // 自动化浏览器的 languages 经常是空数组或只有 ["en-US"]
    try {
        Object.defineProperty(navigator, "languages", {
            get: () => ["zh-CN", "zh", "en"],
            configurable: true,
        });
    } catch (e) {}

    // ─── 3. 模拟 plugins（自动化浏览器是空数组）───
    try {
        const fakePlugins = (() => {
            const list = [
                { name: "PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" },
                { name: "Chrome PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" },
                { name: "Chromium PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" },
                { name: "Microsoft Edge PDF Viewer", filename: "internal-pdf-viewer", description: "Portable Document Format" },
                { name: "WebKit built-in PDF", filename: "internal-pdf-viewer", description: "Portable Document Format" },
            ];
            list.refresh = () => {};
            list.item = (i) => list[i];
            list.namedItem = (n) => list.find((p) => p.name === n) || null;
            Object.defineProperty(list, "length", { get: () => list.length });
            try { Object.setPrototypeOf(list, PluginArray.prototype); } catch (e) {}
            return list;
        })();
        Object.defineProperty(navigator, "plugins", {
            get: () => fakePlugins,
            configurable: true,
        });
    } catch (e) {}

    // ─── 4. 修复 window.chrome.runtime ───
    // 自动化浏览器的 window.chrome 缺少 runtime 子对象（这是 Edge / Chrome 都有的）
    try {
        if (!window.chrome) {
            Object.defineProperty(window, "chrome", {
                value: {},
                writable: true,
                configurable: true,
            });
        }
        if (!window.chrome.runtime) {
            Object.defineProperty(window.chrome, "runtime", {
                value: {
                    OnInstalledReason: {
                        CHROME_UPDATE: "chrome_update",
                        INSTALL: "install",
                        SHARED_MODULE_UPDATE: "shared_module_update",
                        UPDATE: "update",
                    },
                    PlatformArch: { ARM: "arm", ARM64: "arm64", MIPS: "mips", MIPS64: "mips64", X86_32: "x86-32", X86_64: "x86-64" },
                    PlatformOs: { ANDROID: "android", CROS: "cros", LINUX: "linux", MAC: "mac", OPENBSD: "openbsd", WIN: "win" },
                },
                writable: true,
                configurable: true,
            });
        }
    } catch (e) {}

    // ─── 5. 修复 navigator.permissions.query ───
    // 自动化模式下 query 对 notifications 会返回 "denied"，但 Notification.permission 是 "default"
    // 真实浏览器中这两者应该一致
    try {
        const originalQuery = navigator.permissions && navigator.permissions.query;
        if (originalQuery) {
            navigator.permissions.query = (parameters) =>
                parameters && parameters.name === "notifications"
                    ? Promise.resolve({ state: Notification.permission, onchange: null })
                    : originalQuery.call(navigator.permissions, parameters);
        }
    } catch (e) {}

    // ─── 6. WebGL Vendor / Renderer 伪装 ───
    // 自动化模式下 UNMASKED_VENDOR/UNMASKED_RENDERER 经常是 "Google Inc."、"SwiftShader" 这种异常标识
    // 改成常见的 Intel / NVIDIA 显卡
    try {
        const fakeGet = function (origGet, p) {
            // UNMASKED_VENDOR_WEBGL = 37445
            if (p === 37445) return "Google Inc. (Intel)";
            // UNMASKED_RENDERER_WEBGL = 37446
            if (p === 37446) return "ANGLE (Intel, Intel(R) UHD Graphics 630 Direct3D11 vs_5_0 ps_5_0, D3D11)";
            return origGet.apply(this, [p]);
        };
        if (window.WebGLRenderingContext) {
            const origGet = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function (p) {
                return fakeGet.call(this, origGet, p);
            };
        }
        if (window.WebGL2RenderingContext) {
            const origGet2 = WebGL2RenderingContext.prototype.getParameter;
            WebGL2RenderingContext.prototype.getParameter = function (p) {
                return fakeGet.call(this, origGet2, p);
            };
        }
    } catch (e) {}

    // ─── 7. 修正 navigator.platform / userAgentData ───
    // 这两个偶尔被用作检测（特别是 sec-ch-ua-mobile / sec-ch-ua-platform）
    try {
        if (!navigator.platform || navigator.platform === "") {
            Object.defineProperty(navigator, "platform", {
                get: () => "Win32",
                configurable: true,
            });
        }
    } catch (e) {}

    // ─── 8. 隐藏 Function.prototype.toString 的篡改痕迹 ───
    // 上面我们重写了一堆函数，调用 toString 会暴露 "[native code]" 之外的内容
    // 这里把我们的 getter 重新包装一下让它看起来像 native
    try {
        const nativeToString = Function.prototype.toString;
        const nativeToStringStr = nativeToString.call(Object);
        const ignoreList = [
            navigator.webdriver,
            navigator.languages,
            navigator.plugins,
        ];
        Function.prototype.toString = function () {
            if (this && this.name && ignoreList.indexOf(this) !== -1) {
                return `function ${this.name || ""}() { [native code] }`;
            }
            return nativeToString.call(this);
        };
    } catch (e) {}

    // ─── 9. 屏蔽 CDP 的 Runtime.enable 痕迹 ───
    // 反爬有时会用 console.debug 触发 CDP 信号检测
    try {
        const _err = window.console && window.console.error;
        if (_err) {
            window.console.error = function () {
                // 屏蔽 "DevTools failed to load" 之类的日志（这是 CDP 的副作用）
                if (arguments.length > 0 && typeof arguments[0] === "string"
                    && arguments[0].indexOf("DevTools") >= 0) {
                    return;
                }
                return _err.apply(window.console, arguments);
            };
        }
    } catch (e) {}
})();
