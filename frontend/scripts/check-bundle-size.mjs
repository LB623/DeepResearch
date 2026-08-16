import { readdir, stat } from "node:fs/promises";
import path from "node:path";

const assetsDirectory = path.resolve("dist/assets");
const mainChunkLimitBytes = 500_000;
const assets = await readdir(assetsDirectory);
const mainChunks = assets.filter(
  (filename) => /^index-.*\.js$/.test(filename),
);

if (mainChunks.length !== 1) {
  throw new Error(
    `Expected exactly one main index chunk, found: ${mainChunks.join(", ") || "none"}`,
  );
}

const mainChunk = mainChunks[0];
const { size } = await stat(path.join(assetsDirectory, mainChunk));

if (size >= mainChunkLimitBytes) {
  throw new Error(
    `Main chunk ${mainChunk} is ${size} bytes; limit is ${mainChunkLimitBytes} bytes`,
  );
}

console.log(`Main chunk ${mainChunk}: ${size} bytes (< ${mainChunkLimitBytes})`);
