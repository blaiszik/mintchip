import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));

// Reuse local node_modules if present, otherwise sibling mintfig's installed Remotion node_modules
// without modifying anything in mintfig.
const localModules = path.join(here, "node_modules");
const sharedModules = path.resolve(here, "../../../mintfig/promo/demo-video/node_modules");
const modulesDir = existsSync(path.join(localModules, "@remotion/renderer"))
  ? localModules
  : sharedModules;

if (!existsSync(path.join(modulesDir, "@remotion/renderer"))) {
  throw new Error(
    `Could not find @remotion/renderer in ${localModules} or ${sharedModules}. Run npm install first.`,
  );
}

const require = createRequire(path.join(modulesDir, "_anchor.cjs"));
const { bundle } = require("@remotion/bundler");
const { selectComposition, renderFrames, openBrowser } = require("@remotion/renderer");

const outDir = process.argv[2] || "/tmp/mintchip_remotion_opener";
const concurrency = Number(process.argv[3] || "4");
const bundleDir = process.argv[4] || "/tmp/mintchip_remotion_bundle";

const entryPoint = path.join(here, "src", "index.ts");

console.log(`Bundling ${entryPoint} using modules from ${modulesDir}...`);
const serveUrl = await bundle({
  entryPoint,
  outDir: bundleDir,
  webpackOverride: (config) => ({
    ...config,
    resolve: {
      ...config.resolve,
      modules: [
        ...(config.resolve?.modules ?? ["node_modules"]),
        modulesDir,
      ],
    },
    resolveLoader: {
      ...config.resolveLoader,
      modules: [
        ...(config.resolveLoader?.modules ?? ["node_modules"]),
        modulesDir,
      ],
    },
  }),
});

const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browserExecutable = existsSync(systemChrome) ? systemChrome : null;

const browser = await openBrowser("chrome", {
  browserExecutable,
  chromeMode: "chrome-for-testing",
  logLevel: "error",
});

try {
  if (existsSync(outDir)) rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });

  const composition = await selectComposition({
    serveUrl,
    id: "MintchipOpener",
    puppeteerInstance: browser,
    logLevel: "error",
  });
  console.log(
    `Rendering ${composition.id} (${composition.width}x${composition.height} @ ${composition.fps}fps, ${composition.durationInFrames} frames)...`,
  );

  await renderFrames({
    composition,
    serveUrl,
    outputDir: outDir,
    imageFormat: "png",
    puppeteerInstance: browser,
    concurrency,
    logLevel: "error",
    onStart: () => {},
    onFrameUpdate: (done) => {
      if (done % 45 === 0 || done === composition.durationInFrames) {
        console.log(`  ${composition.id}: ${done}/${composition.durationInFrames}`);
      }
    },
  });
} finally {
  await browser.close({ silent: true });
}
console.log(`Done rendering lossless PNG sequence to ${outDir}.`);
