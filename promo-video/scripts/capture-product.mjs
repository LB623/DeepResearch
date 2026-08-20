// Capture the real DeepResearch frontend components against fixed, fictional
// Orion-7 fixtures. Browser traffic is restricted to the local Vite harness;
// /api/models is fulfilled in-process and no backend is contacted.

import { createHash } from "node:crypto";
import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import puppeteer from "puppeteer-core";

const here = path.dirname(fileURLToPath(import.meta.url));
const promoRoot = path.resolve(here, "..");
const workspace = path.resolve(promoRoot, "..");

const CONFIG = {
  base: "http://127.0.0.1:4179",
  harnessRoot: path.join(promoRoot, "capture-app"),
  viteBin: path.join(workspace, "frontend/node_modules/.bin/vite"),
  viteConfig: path.join(promoRoot, "capture-app/vite.config.ts"),
  liveOutDir: path.join(promoRoot, "public/textures/live"),
  liveLayoutJson: path.join(promoRoot, "src/live-layout.json"),
  viewport: { width: 1920, height: 1080, deviceScaleFactor: 2 },
  settleMs: 650,
  chromeCandidates: [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
  ].filter(Boolean),
  sourceFiles: [
    "frontend/src/global.css",
    "frontend/src/components/WelcomeScreen.tsx",
    "frontend/src/components/InputForm.tsx",
    "frontend/src/components/ActivityTimeline.tsx",
    "frontend/src/components/ChatMessagesView.tsx",
    "frontend/src/lib/api.ts",
    "frontend/public/research-mark.svg",
    "frontend/package-lock.json",
    "promo-video/capture-app/index.html",
    "promo-video/capture-app/src/main.tsx",
    "promo-video/capture-app/src/capture.css",
    "promo-video/capture-app/vite.config.ts",
    "promo-video/capture-app/tsconfig.json",
    "promo-video/scripts/capture-product.mjs",
  ],
  searchQuery:
    "分析虚构的 Orion-7 推理引擎：架构取舍、生态依赖与潜在风险",
  pages: [
    {
      name: "search",
      path: "/?page=search",
      proofText: "把复杂问题，",
      boxes: {
        input: '[data-page="search"] form > div:first-child',
        form: '[data-page="search"] form',
        evidence: '[data-capture="search-evidence"]',
      },
      cutouts: [
        {
          file: "search-input.png",
          selector: '[data-page="search"] form > div:first-child',
          boxKey: "input",
          omitBackground: true,
        },
        {
          file: "search-evidence.png",
          selector: '[data-capture="search-evidence"]',
          boxKey: "evidence",
        },
      ],
    },
    {
      name: "workflow",
      path: "/?page=workflow",
      proofText: "已完成 · 5 个阶段",
      boxes: {
        timeline: '[data-capture="workflow-timeline"]',
        event1: '[data-capture="workflow-event1"]',
        event2: '[data-capture="workflow-event2"]',
        event3: '[data-capture="workflow-event3"]',
        event4: '[data-capture="workflow-event4"]',
        event5: '[data-capture="workflow-event5"]',
      },
      cutouts: [
        {
          file: "workflow-timeline.png",
          selector: '[data-capture="workflow-timeline"]',
          boxKey: "timeline",
        },
        ...Array.from({ length: 5 }, (_, index) => ({
          file: `workflow-event${index + 1}.png`,
          selector: `[data-capture="workflow-event${index + 1}"]`,
          boxKey: `event${index + 1}`,
          omitBackground: true,
        })),
      ],
    },
    {
      name: "report",
      path: "/?page=report",
      proofText: "复制报告",
      blankFullFile: "report-blank-full.png",
      boxes: {
        document: '[data-capture="report-document"]',
        table: '[data-capture="report-table"]',
        references: [
          '[data-capture="report-references-heading"]',
          '[data-capture="report-references-content"]',
        ],
      },
      cutouts: [
        {
          file: "report-document.png",
          selector: '[data-capture="report-document"]',
          boxKey: "document",
        },
        {
          file: "report-table.png",
          selector: '[data-capture="report-table"]',
          boxKey: "table",
        },
        {
          file: "report-references.png",
          selectors: [
            '[data-capture="report-references-heading"]',
            '[data-capture="report-references-content"]',
          ],
          boxKey: "references",
        },
      ],
    },
  ],
};

const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const pathExists = async (target) => {
  try {
    await fs.access(target);
    return true;
  } catch {
    return false;
  }
};

const sha256File = async (target) => {
  const hash = createHash("sha256");
  hash.update(await fs.readFile(target));
  return hash.digest("hex");
};

const pngDimensions = async (target) => {
  const bytes = await fs.readFile(target);
  const signature = "89504e470d0a1a0a";
  if (bytes.length < 24 || bytes.subarray(0, 8).toString("hex") !== signature) {
    throw new Error(`Invalid PNG file: ${target}`);
  }
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
    bytes: bytes.length,
  };
};

let chromePath;
for (const candidate of CONFIG.chromeCandidates) {
  if (await pathExists(candidate)) {
    chromePath = candidate;
    break;
  }
}

if (!chromePath) {
  throw new Error(
    `No local Chrome executable found. Checked: ${CONFIG.chromeCandidates.join(", ")}`,
  );
}

const stagingRoot = await fs.mkdtemp(path.join(promoRoot, ".capture-staging-"));
const stagingOutDir = path.join(stagingRoot, "textures");
const stagingLayoutJson = path.join(stagingRoot, "live-layout.json");
await fs.mkdir(stagingOutDir, { recursive: true });

const vite = spawn(
  CONFIG.viteBin,
  [
    "--config",
    CONFIG.viteConfig,
    "--host",
    "127.0.0.1",
    "--port",
    "4179",
    "--strictPort",
  ],
  {
    cwd: CONFIG.harnessRoot,
    stdio: ["ignore", "pipe", "pipe"],
  },
);

let viteOutput = "";
vite.stdout.on("data", (chunk) => {
  viteOutput += chunk.toString();
});
vite.stderr.on("data", (chunk) => {
  viteOutput += chunk.toString();
});

const stopVite = () => {
  if (!vite.killed && vite.exitCode === null) vite.kill("SIGTERM");
};

const handleSignal = () => {
  stopVite();
  process.exitCode = 130;
};
process.once("SIGINT", handleSignal);
process.once("SIGTERM", handleSignal);

const waitForHarness = async () => {
  for (let attempt = 0; attempt < 80; attempt += 1) {
    if (vite.exitCode !== null) {
      throw new Error(`Capture harness exited early.\n${viteOutput}`);
    }
    try {
      const response = await fetch(CONFIG.base);
      if (response.ok) return;
    } catch {
      // The loopback-only harness is still starting.
    }
    await delay(125);
  }
  throw new Error(`Timed out waiting for ${CONFIG.base}.\n${viteOutput}`);
};

const elementBox = async (page, selector) => {
  const handles = await page.$$(selector);
  if (handles.length !== 1) {
    await Promise.all(handles.map((handle) => handle.dispose()));
    throw new Error(
      `Expected exactly one capture element for ${selector}; found ${handles.length}`,
    );
  }
  const handle = handles[0];
  const box = await handle.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    return {
      x: rect.x + window.scrollX,
      y: rect.y + window.scrollY,
      w: rect.width,
      h: rect.height,
    };
  });
  await handle.dispose();
  return box;
};

const unionBox = async (page, selectors) => {
  const boxes = [];
  for (const selector of selectors) boxes.push(await elementBox(page, selector));
  const left = Math.min(...boxes.map((box) => box.x));
  const top = Math.min(...boxes.map((box) => box.y));
  const right = Math.max(...boxes.map((box) => box.x + box.w));
  const bottom = Math.max(...boxes.map((box) => box.y + box.h));
  return { x: left, y: top, w: right - left, h: bottom - top };
};

const assertValidBox = (pageName, key, box) => {
  const values = [box.x, box.y, box.w, box.h];
  if (!values.every((value) => Number.isFinite(value)) || box.w <= 0 || box.h <= 0) {
    throw new Error(`${pageName}.${key} has an invalid box: ${JSON.stringify(box)}`);
  }
  const tolerance = 1;
  if (
    box.x < -tolerance ||
    box.y < -tolerance ||
    box.x + box.w > CONFIG.viewport.width + tolerance ||
    box.y + box.h > CONFIG.viewport.height + tolerance
  ) {
    throw new Error(`${pageName}.${key} falls outside the capture viewport`);
  }
};

const screenshotRegion = async (page, capture) => {
  const output = path.join(stagingOutDir, capture.file);
  if (capture.selector) {
    const handles = await page.$$(capture.selector);
    if (handles.length !== 1) {
      await Promise.all(handles.map((handle) => handle.dispose()));
      throw new Error(
        `Expected exactly one cutout element for ${capture.selector}; found ${handles.length}`,
      );
    }
    await handles[0].screenshot({
      path: output,
      omitBackground: Boolean(capture.omitBackground),
    });
    await handles[0].dispose();
    return;
  }

  const box = await unionBox(page, capture.selectors);
  await page.screenshot({
    path: output,
    clip: { x: box.x, y: box.y, width: box.w, height: box.h },
    omitBackground: Boolean(capture.omitBackground),
  });
};

const validatePageData = async (page, capturePage) => {
  const facts = await page.evaluate(
    ({ pageName, proofText }) => {
      const text = document.body.innerText;
      const mark = document.querySelector("img.capture-brand-mark");
      const rootStyle = getComputedStyle(document.documentElement);
      const links = [...document.querySelectorAll("a[href]")]
        .map((anchor) => anchor.href)
        .filter((href) => {
          try {
            const url = new URL(href);
            return (
              (url.protocol === "http:" || url.protocol === "https:") &&
              !url.hostname.endsWith(".example.invalid")
            );
          } catch {
            return true;
          }
        });
      return {
        pageMarkerCount: document.querySelectorAll(`[data-page="${pageName}"]`).length,
        fixtureMarkerCount: document.querySelectorAll(
          '[data-fixture="fictional-orion-7"]',
        ).length,
        demoMarker: text.includes("DEMO DATA · FICTIONAL"),
        fictionalCopy: text.includes("虚构") && text.includes("Orion-7"),
        currentComponentProof: text.includes(proofText),
        brand: {
          count: document.querySelectorAll("img.capture-brand-mark").length,
          loaded:
            mark instanceof HTMLImageElement &&
            mark.complete &&
            mark.naturalWidth > 0 &&
            mark.naturalHeight > 0,
          source: mark instanceof HTMLImageElement ? new URL(mark.currentSrc).pathname : "",
          renderedSize:
            mark instanceof HTMLImageElement
              ? {
                  width: mark.getBoundingClientRect().width,
                  height: mark.getBoundingClientRect().height,
                }
              : null,
        },
        theme: {
          htmlClass: document.documentElement.className,
          background: rootStyle.getPropertyValue("--background").trim(),
          foreground: rootStyle.getPropertyValue("--foreground").trim(),
          primary: rootStyle.getPropertyValue("--primary").trim(),
          colorScheme: rootStyle.colorScheme,
        },
        unexpectedLinks: links,
      };
    },
    { pageName: capturePage.name, proofText: capturePage.proofText },
  );

  if (facts.pageMarkerCount !== 1 || facts.fixtureMarkerCount !== 1) {
    throw new Error(`${capturePage.name} is missing an exact page or fixture marker`);
  }
  if (!facts.demoMarker || !facts.fictionalCopy) {
    throw new Error(`${capturePage.name} does not visibly identify its fictional demo data`);
  }
  if (!facts.currentComponentProof) {
    throw new Error(`${capturePage.name} is missing current-component proof text`);
  }
  if (
    facts.brand.count !== 1 ||
    !facts.brand.loaded ||
    facts.brand.source !== "/research-mark.svg" ||
    facts.brand.renderedSize?.width !== 32 ||
    facts.brand.renderedSize?.height !== 32
  ) {
    throw new Error(`${capturePage.name} did not load the official research-mark.svg`);
  }
  if (
    facts.theme.htmlClass.includes("dark") ||
    facts.theme.background.toLowerCase() !== "#f3f5f4" ||
    facts.theme.primary.toLowerCase() !== "#1d6f5f" ||
    facts.theme.colorScheme !== "light"
  ) {
    throw new Error(
      `${capturePage.name} is not using the current light gray/green frontend theme`,
    );
  }
  if (facts.unexpectedLinks.length > 0) {
    throw new Error(
      `${capturePage.name} contains non-fixture external links: ${facts.unexpectedLinks.join(", ")}`,
    );
  }
  return facts;
};

const validateStagedFiles = async (layout) => {
  const expectations = new Map();
  for (const capturePage of CONFIG.pages) {
    expectations.set(`${capturePage.name}-full.png`, {
      width: CONFIG.viewport.width * CONFIG.viewport.deviceScaleFactor,
      height: CONFIG.viewport.height * CONFIG.viewport.deviceScaleFactor,
      exact: true,
    });
    if (capturePage.blankFullFile) {
      expectations.set(capturePage.blankFullFile, {
        width: CONFIG.viewport.width * CONFIG.viewport.deviceScaleFactor,
        height: CONFIG.viewport.height * CONFIG.viewport.deviceScaleFactor,
        exact: true,
      });
    }
    for (const cutout of capturePage.cutouts) {
      const box = layout[capturePage.name][cutout.boxKey];
      expectations.set(cutout.file, {
        width: Math.round(box.w * CONFIG.viewport.deviceScaleFactor),
        height: Math.round(box.h * CONFIG.viewport.deviceScaleFactor),
        exact: false,
      });
    }
  }

  const actualFiles = (await fs.readdir(stagingOutDir)).sort();
  const expectedFiles = [...expectations.keys()].sort();
  if (JSON.stringify(actualFiles) !== JSON.stringify(expectedFiles)) {
    throw new Error(
      `Staged capture file set mismatch. Expected ${expectedFiles.join(", ")}; got ${actualFiles.join(", ")}`,
    );
  }

  const manifest = {};
  for (const [file, expected] of expectations) {
    const target = path.join(stagingOutDir, file);
    const dimensions = await pngDimensions(target);
    const tolerance = expected.exact ? 0 : 2;
    if (
      Math.abs(dimensions.width - expected.width) > tolerance ||
      Math.abs(dimensions.height - expected.height) > tolerance ||
      dimensions.bytes < 1024
    ) {
      throw new Error(
        `${file} failed dimensions/content validation: ${JSON.stringify(dimensions)}`,
      );
    }
    manifest[file] = {
      ...dimensions,
      sha256: await sha256File(target),
    };
  }
  return manifest;
};

const publishAtomically = async () => {
  await fs.mkdir(path.dirname(CONFIG.liveOutDir), { recursive: true });
  await fs.mkdir(path.dirname(CONFIG.liveLayoutJson), { recursive: true });

  const previousOut = path.join(stagingRoot, "previous-live");
  const previousLayout = path.join(stagingRoot, "previous-live-layout.json");
  let backedUpOut = false;
  let backedUpLayout = false;
  let installedOut = false;
  let installedLayout = false;

  try {
    if (await pathExists(CONFIG.liveOutDir)) {
      await fs.rename(CONFIG.liveOutDir, previousOut);
      backedUpOut = true;
    }
    if (await pathExists(CONFIG.liveLayoutJson)) {
      await fs.rename(CONFIG.liveLayoutJson, previousLayout);
      backedUpLayout = true;
    }

    await fs.rename(stagingOutDir, CONFIG.liveOutDir);
    installedOut = true;
    await fs.rename(stagingLayoutJson, CONFIG.liveLayoutJson);
    installedLayout = true;
  } catch (publishError) {
    const rollbackErrors = [];
    const rollback = async (operation) => {
      try {
        await operation();
      } catch (error) {
        rollbackErrors.push(error);
      }
    };

    if (installedLayout && (await pathExists(CONFIG.liveLayoutJson))) {
      await rollback(() => fs.rename(CONFIG.liveLayoutJson, stagingLayoutJson));
    }
    if (installedOut && (await pathExists(CONFIG.liveOutDir))) {
      await rollback(() => fs.rename(CONFIG.liveOutDir, stagingOutDir));
    }
    if (backedUpLayout && (await pathExists(previousLayout))) {
      await rollback(() => fs.rename(previousLayout, CONFIG.liveLayoutJson));
    }
    if (backedUpOut && (await pathExists(previousOut))) {
      await rollback(() => fs.rename(previousOut, CONFIG.liveOutDir));
    }
    if (rollbackErrors.length > 0) {
      throw new AggregateError(
        [publishError, ...rollbackErrors],
        "Capture publish failed and rollback was incomplete",
      );
    }
    throw publishError;
  }

  if (backedUpOut) await fs.rm(previousOut, { recursive: true, force: true });
  if (backedUpLayout) await fs.rm(previousLayout, { force: true });
};

let browser;
try {
  await waitForHarness();
  browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: true,
    args: [
      "--disable-background-networking",
      "--disable-component-update",
      "--disable-sync",
      "--no-first-run",
      "--host-resolver-rules=MAP * 0.0.0.0, EXCLUDE 127.0.0.1, EXCLUDE localhost",
    ],
  });

  const page = await browser.newPage();
  await page.setViewport(CONFIG.viewport);
  await page.emulateMediaFeatures([
    { name: "prefers-reduced-motion", value: "reduce" },
  ]);
  await page.setCacheEnabled(false);
  await page.setRequestInterception(true);

  const unexpectedRequests = [];
  let modelFixtureRequests = 0;
  page.on("request", (request) => {
    void (async () => {
      const url = new URL(request.url());
      const isHarnessRequest =
        url.protocol === "http:" &&
        url.hostname === "127.0.0.1" &&
        url.port === "4179";
      const isModelsFixture =
        request.method() === "GET" &&
        url.protocol === "http:" &&
        url.hostname === "localhost" &&
        url.port === "2024" &&
        url.pathname === "/api/models" &&
        url.search === "";

      if (isHarnessRequest) {
        await request.continue();
        return;
      }
      if (isModelsFixture) {
        modelFixtureRequests += 1;
        await request.respond({
          status: 200,
          contentType: "application/json",
          headers: {
            "access-control-allow-origin": CONFIG.base,
            "cache-control": "no-store",
          },
          body: JSON.stringify({
            models: [
              {
                model_id: "orion-7-reasoner",
                display_name: "Orion-7 Reasoner",
                icon: "Cpu",
                icon_color: "green-700",
              },
            ],
          }),
        });
        return;
      }
      unexpectedRequests.push(`${request.method()} ${request.url()}`);
      await request.abort("blockedbyclient");
    })().catch((error) => {
      unexpectedRequests.push(`interception error: ${String(error)}`);
    });
  });

  const pageErrors = [];
  page.on("pageerror", (error) => pageErrors.push(String(error)));

  const layout = {
    pageW: CONFIG.viewport.width,
    dpr: CONFIG.viewport.deviceScaleFactor,
  };
  const pageProof = {};

  for (const capturePage of CONFIG.pages) {
    await page.goto(`${CONFIG.base}${capturePage.path}`, {
      waitUntil: "networkidle0",
    });
    await page.waitForFunction(
      () =>
        window.__CAPTURE_READY__ === true ||
        typeof window.__CAPTURE_ERROR__ === "string",
      { timeout: 10_000 },
    );
    const captureError = await page.evaluate(() => window.__CAPTURE_ERROR__);
    if (captureError) throw new Error(`${capturePage.name}: ${captureError}`);
    await page.evaluate(() => document.fonts.ready);
    await delay(CONFIG.settleMs);

    if (capturePage.name === "search") {
      await page.waitForSelector('[data-page="search"] textarea');
      await page.$eval(
        '[data-page="search"] textarea',
        (textarea, value) => {
          const setter = Object.getOwnPropertyDescriptor(
            HTMLTextAreaElement.prototype,
            "value",
          )?.set;
          setter?.call(textarea, value);
          textarea.dispatchEvent(new Event("input", { bubbles: true }));
          textarea.dispatchEvent(new Event("change", { bubbles: true }));
        },
        CONFIG.searchQuery,
      );
      await page.waitForFunction(
        (query) => document.querySelector("textarea")?.value === query,
        {},
        CONFIG.searchQuery,
      );
      await delay(100);
    }

    if (capturePage.name === "report") {
      await page.$eval('[data-page="report"] textarea', (textarea) => {
        textarea.placeholder =
          "基于虚构资料，继续分析 Orion-7 的运行时兼容边界…";
      });
    }

    pageProof[capturePage.name] = await validatePageData(page, capturePage);
    const pageH = await page.evaluate(() => document.documentElement.scrollHeight);
    if (pageH !== CONFIG.viewport.height) {
      throw new Error(
        `${capturePage.name} page height is ${pageH}px; expected ${CONFIG.viewport.height}px`,
      );
    }

    const entry = { pageH };
    for (const [key, selectorOrSelectors] of Object.entries(capturePage.boxes)) {
      const box = Array.isArray(selectorOrSelectors)
        ? await unionBox(page, selectorOrSelectors)
        : await elementBox(page, selectorOrSelectors);
      assertValidBox(capturePage.name, key, box);
      entry[key] = box;
    }
    layout[capturePage.name] = entry;

    await page.screenshot({
      path: path.join(stagingOutDir, `${capturePage.name}-full.png`),
      fullPage: true,
      captureBeyondViewport: true,
    });
    for (const cutout of capturePage.cutouts) {
      await screenshotRegion(page, cutout);
    }
    if (capturePage.blankFullFile) {
      const documentSelector = capturePage.boxes.document;
      await page.$eval(documentSelector, (documentElement) => {
        documentElement.style.visibility = "hidden";
      });
      await page.screenshot({
        path: path.join(stagingOutDir, capturePage.blankFullFile),
        fullPage: true,
        captureBeyondViewport: true,
      });
      await page.$eval(documentSelector, (documentElement) => {
        documentElement.style.removeProperty("visibility");
      });
    }
    console.log(
      `staged ${capturePage.name} (${CONFIG.viewport.width}x${pageH} @${CONFIG.viewport.deviceScaleFactor}x)`,
    );
  }

  if (unexpectedRequests.length > 0) {
    throw new Error(
      `Unexpected network requests were blocked:\n${unexpectedRequests.join("\n")}`,
    );
  }
  if (modelFixtureRequests !== 2) {
    throw new Error(
      `Expected two local /api/models fixture requests; observed ${modelFixtureRequests}`,
    );
  }
  if (pageErrors.length > 0) {
    throw new Error(`Capture pages raised errors:\n${pageErrors.join("\n")}`);
  }

  const assets = await validateStagedFiles(layout);
  const sources = {};
  for (const relativePath of CONFIG.sourceFiles) {
    sources[relativePath] = await sha256File(path.join(workspace, relativePath));
  }
  layout._capture = {
    schemaVersion: 2,
    capturedAt: new Date().toISOString(),
    fixture: "fictional-orion-7",
    frontendTheme: "light-gray-green",
    networkPolicy: "loopback-harness-and-in-process-model-fixture-only",
    modelFixtureRequests,
    sources,
    pageProof,
    assets,
  };

  await fs.writeFile(stagingLayoutJson, `${JSON.stringify(layout, null, 2)}\n`);
  const writtenLayout = JSON.parse(await fs.readFile(stagingLayoutJson, "utf8"));
  if (
    writtenLayout.pageW !== CONFIG.viewport.width ||
    writtenLayout.dpr !== CONFIG.viewport.deviceScaleFactor ||
    writtenLayout._capture?.fixture !== "fictional-orion-7"
  ) {
    throw new Error("Staged layout manifest failed round-trip validation");
  }

  await publishAtomically();
  console.log(`published ${CONFIG.liveOutDir}`);
  console.log(`published ${CONFIG.liveLayoutJson}`);
} finally {
  if (browser) await browser.close();
  stopVite();
  process.off("SIGINT", handleSignal);
  process.off("SIGTERM", handleSignal);
  await fs.rm(stagingRoot, { recursive: true, force: true });
}
