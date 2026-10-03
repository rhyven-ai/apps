// SPDX-License-Identifier: Apache-2.0
import { readFileSync, writeFileSync, existsSync, renameSync } from 'node:fs';
import { join } from 'node:path';
import { createHash } from 'node:crypto';

const request = JSON.parse(readFileSync(0, 'utf8'));
if (request.protocol !== 'rhyven.action/1' || request.function !== 'action_analyze') {
  throw new Error('Unsupported action protocol');
}
const text = request.args.text;
const counter = join(process.env.RHYVEN_DATA_DIR, 'calls.json');
const calls = existsSync(counter) ? JSON.parse(readFileSync(counter, 'utf8')) + 1 : 1;
writeFileSync(counter + '.tmp', JSON.stringify(calls));
renameSync(counter + '.tmp', counter);
console.log(JSON.stringify({ result: {
  words: text.trim() ? text.trim().split(/\s+/u).length : 0,
  sha256: createHash('sha256').update(text).digest('hex'),
  calls,
} }));
