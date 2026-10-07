import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const context = { window: {}, Intl };
vm.createContext(context);
for (const file of ['catalog-model.js', 'organization.js']) {
  vm.runInContext(fs.readFileSync(path.join(root, 'web', file), 'utf8'), context);
}
for (const file of ['app.js', 'chat-controls.js']) {
  new Function(fs.readFileSync(path.join(root, 'web', file), 'utf8'));
}
const html = fs.readFileSync(path.join(root, 'web', 'index.html'), 'utf8');
assert.match(html, /<select id="group"[^>]*><option value="projects">ChatGPT Projects<\/option>/);

const catalog = context.window.CatalogModel;
const order = context.window.SidebarOrder;
const title = chat => chat.alias || chat.title;
const kind = chat => chat.kind;
const ids = rows => Array.from(rows, chat => chat.id);
const chats = [
  { id: 'research-pin', title: 'Zulu', project: 'Research', folder: 'C:/exports/Research', category: 'Pinned notes', kind: 'work', pinned: 1, created: 1 },
  { id: 'research-a', title: 'Alpha', project: 'Research', folder: 'C:/exports/Research', category: 'Reading', kind: 'work', created: 20 },
  { id: 'research-b', title: 'Beta', project: 'Research', folder: 'C:/exports/Research', category: 'Personal', kind: 'work', created: 10 },
  { id: 'research-chat', title: 'Quick question', project: 'Research', folder: 'C:/exports/Research', category: 'Personal', kind: 'chat', created: 30 },
  { id: 'writing', title: 'Draft', project: 'Writing', folder: 'C:/exports/Writing', category: 'Reading', kind: 'work', created: 40 },
  { id: 'outside', title: 'Outside project', project: '', folder: 'C:/exports/Research', category: 'General', kind: 'work', created: 50 },
];
const settings = { groupSort: { 'projects|project:Research': 'title' } };
const original = JSON.stringify(chats);

const projectFilter = catalog.filter(chats, { projects: 'only' }, {}, title);
const workGroups = order.groups(projectFilter, settings, 'work', 'projects', true, kind, title, 'oldest');
assert.deepEqual(Array.from(workGroups.keys()), ['pinned', 'project:Research', 'project:Writing']);
assert.deepEqual(ids(workGroups.get('pinned')), ['research-pin']);
assert.deepEqual(ids(workGroups.get('project:Research')), ['research-a', 'research-b']);
assert.deepEqual(ids(workGroups.get('project:Writing')), ['writing']);

const chatGroups = order.groups(projectFilter, settings, 'chat', 'projects', true, kind, title, 'oldest');
assert.deepEqual(Array.from(chatGroups.keys()), ['project:Research']);
assert.deepEqual(ids(chatGroups.get('project:Research')), ['research-chat']);

const hiddenProjects = order.groups(chats, {}, 'all', 'projects', false, kind, title, 'newest');
assert.deepEqual(Array.from(hiddenProjects.keys()), ['uncategorized']);
assert.deepEqual(ids(hiddenProjects.get('uncategorized')), ['outside']);

const diskGroups = order.groups(chats, {}, 'all', 'folders', true, kind, title, 'newest');
assert.deepEqual(ids(diskGroups.get('folder:C:/exports/Research')).sort(), ['outside', 'research-a', 'research-b', 'research-chat'].sort());
assert(!Array.from(diskGroups.keys()).some(key => key.startsWith('project:')));
const diskGroupsWithoutProjects = order.groups(chats, {}, 'all', 'folders', false, kind, title, 'newest');
assert.deepEqual(ids(diskGroupsWithoutProjects.get('folder:C:/exports/Research')), ['outside']);

const researchRows = workGroups.get('project:Research');
const reordered = order.rowOrderChanges(researchRows, researchRows[1], researchRows[0], 'projects', kind);
assert.deepEqual(ids(reordered), ['research-b', 'research-a']);
assert.deepEqual(Array.from(reordered, change => change.position), [0, 10]);
assert(!Object.hasOwn(reordered[0], 'category'));
assert.equal(order.rowOrderChanges(researchRows, chats[4], researchRows[0], 'projects', kind), null);
assert.equal(order.canDropChat(chats[4], researchRows[0], 'projects', kind), false);

const categoryMove = order.rowOrderChanges([chats[1]], chats[5], chats[1], 'categories', kind);
assert.equal(categoryMove.find(change => change.id === 'outside').category, 'Reading');
assert.equal(JSON.stringify(chats), original);

console.log('Native Projects grouping, filter/type/sort composition, Disk folders, and project drag/drop checks passed.');
