import test from "node:test";
import assert from "node:assert/strict";
import { writeFileSync, symlinkSync } from "node:fs";
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
