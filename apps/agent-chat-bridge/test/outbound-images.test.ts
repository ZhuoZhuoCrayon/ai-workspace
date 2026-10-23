import test from "node:test";
import assert from "node:assert/strict";
import fs, { writeFileSync, symlinkSync, mkdirSync, renameSync } from "node:fs";
import { syncBuiltinESMExports } from "node:module";
import { join } from "node:path";
import { extractImages } from "../src/channels/outbound-images.js";
import { temporary } from "./helpers.js";

test("出站图片检查真实路径、类型与去重，拒绝 symlink 越界", () => {
  const temp = temporary(),
    outside = temporary(),
    image = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 0]);
  try {
    const path = join(temp.directory, "image.png");
    writeFileSync(path, image);
    const extracted = extractImages(
      `说明\n![图片](${path})\n![重复](${path})`,
      temp.directory,
    );
    assert.equal(extracted.images.length, 1);
    assert.equal(extracted.text, "说明");
    const privateFile = join(outside.directory, "private.png");
    writeFileSync(privateFile, image);
    const link = join(temp.directory, "link.png");
    symlinkSync(privateFile, link);
    const rejected = extractImages(`![越界](${link})`, temp.directory);
    assert.equal(rejected.images.length, 0);
    assert.match(rejected.text, /不在允许/);
    const fake = join(temp.directory, "fake.png");
    writeFileSync(fake, "not image");
    assert.equal(
      extractImages(`![](${fake})`, temp.directory).images.length,
      0,
    );
  } finally {
    temp.cleanup();
    outside.cleanup();
  }
});

test("目录在检查与打开之间被替换时，按打开的文件描述符拒绝越界读取", () => {
  const temp = temporary(),
    outside = temporary();
  const directory = join(temp.directory, "nested");
  mkdirSync(directory);
  const image = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 0]);
  const path = join(directory, "image.png");
  writeFileSync(path, image);
  writeFileSync(join(outside.directory, "image.png"), image);
  const original = fs.openSync;
  try {
    fs.openSync = ((name: fs.PathLike, ...args: unknown[]) => {
      if (String(name) === path) {
        renameSync(directory, directory + ".old");
        symlinkSync(outside.directory, directory);
      }
      return (original as (...args: unknown[]) => number)(name, ...args);
    }) as typeof fs.openSync;
    syncBuiltinESMExports();
    const result = extractImages(`![race](${path})`, temp.directory);
    assert.equal(result.images.length, 0);
    assert.match(result.text, /不在允许/);
  } finally {
    fs.openSync = original;
    syncBuiltinESMExports();
    temp.cleanup();
    outside.cleanup();
  }
});

test("已固定的工作目录被替换为符号链接后，不把新目录作为图片授权根", () => {
  const temp = temporary(),
    outside = temporary();
  try {
    writeFileSync(
      join(outside.directory, "image.png"),
      Buffer.from([137, 80, 78, 71, 13, 10, 26, 10, 0]),
    );
    const workspace = join(temp.directory, "workspace");
    symlinkSync(outside.directory, workspace);
    const result = extractImages(
      `![private](${join(workspace, "image.png")})`,
      workspace,
    );
    assert.equal(result.images.length, 0);
    assert.match(result.text, /目录已变更/);
  } finally {
    temp.cleanup();
    outside.cleanup();
  }
});
