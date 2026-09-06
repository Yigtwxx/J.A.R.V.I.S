/**
 * Put the Spatial tab's on-device models where the browser can reach them.
 *
 * Everything the hand tracker and the room detector need is served from our own
 * origin, never a CDN: the console has to work with no internet, and a gesture
 * layer that silently stops when a third party is unreachable is worse than one
 * that never started.
 *
 * The assets are ~42 MB, so they are gitignored and restored by this script:
 *   npm run spatial:assets
 */

import { createWriteStream } from 'node:fs';
import { access, cp, mkdir, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { pipeline } from 'node:stream/promises';
import { fileURLToPath } from 'node:url';
import { Readable } from 'node:stream';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WASM_SRC = join(ROOT, 'node_modules', '@mediapipe', 'tasks-vision', 'wasm');
const WASM_DEST = join(ROOT, 'public', 'mediapipe', 'wasm');
const MODEL_DIR = join(ROOT, 'public', 'models');

/** Pinned to a version, never `latest`: a silently swapped model changes every
 *  gesture threshold that was tuned against it. */
const MODELS = [
    {
        file: 'hand_landmarker.task',
        url: 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task',
        minBytes: 5_000_000,
    },
    {
        file: 'efficientdet_lite0.tflite',
        url: 'https://storage.googleapis.com/mediapipe-models/object_detector/efficientdet_lite0/float16/1/efficientdet_lite0.tflite',
        minBytes: 4_000_000,
    },
];

const exists = async (path) => {
    try {
        await access(path);
        return true;
    } catch {
        return false;
    }
};

const copyWasm = async () => {
    if (!(await exists(WASM_SRC))) {
        throw new Error(
            `@mediapipe/tasks-vision is not installed — run \`npm install\` first (looked in ${WASM_SRC}).`
        );
    }
    await mkdir(WASM_DEST, { recursive: true });
    await cp(WASM_SRC, WASM_DEST, { recursive: true });
    console.log(`✓ wasm  → public/mediapipe/wasm`);
};

const download = async ({ file, url, minBytes }) => {
    const dest = join(MODEL_DIR, file);
    if (await exists(dest)) {
        const { size } = await stat(dest);
        // A truncated download is worse than a missing one: MediaPipe fails
        // deep inside the WASM with an unreadable message.
        if (size >= minBytes) {
            console.log(`· ${file} already present (${(size / 1e6).toFixed(1)} MB)`);
            return;
        }
        console.log(`! ${file} looks truncated (${size} bytes) — fetching again`);
    }

    const response = await fetch(url);
    if (!response.ok || !response.body) {
        throw new Error(`Could not fetch ${file}: HTTP ${response.status}`);
    }
    await mkdir(MODEL_DIR, { recursive: true });
    await pipeline(Readable.fromWeb(response.body), createWriteStream(dest));

    const { size } = await stat(dest);
    if (size < minBytes) throw new Error(`${file} downloaded short (${size} bytes)`);
    console.log(`✓ ${file} (${(size / 1e6).toFixed(1)} MB)`);
};

await copyWasm();
for (const model of MODELS) await download(model);
console.log('Spatial assets ready.');
