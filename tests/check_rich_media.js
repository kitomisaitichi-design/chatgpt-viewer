const assert=require('assert'),vm=require('vm'),fs=require('fs'),path=require('path');
const c={window:{addEventListener(){}},location:{href:'http://127.0.0.1:1234/',origin:'http://127.0.0.1:1234'},URL,URLSearchParams};vm.createContext(c);for(const file of ['midi-player.js','rich-media.js','structured-content.js','widgets.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),c);
const midi=Buffer.from('4d546864000000060000000100604d54726b0000001000903c6460803c000090406460804000','hex'); // two half-second notes
const buffer=midi.buffer.slice(midi.byteOffset,midi.byteOffset+midi.length);new DataView(buffer).setUint32(18,Buffer.from(buffer).length-22);
const parsed=c.MidiPlayer.parse(buffer);assert.equal(parsed.notes.length,2);assert.equal(parsed.notes[0].note,60);assert.equal(parsed.notes[0].end,.5);assert.equal(parsed.notes[1].start,.5);assert.equal(parsed.duration,1);
assert.throws(()=>c.MidiPlayer.parse(new ArrayBuffer(2)),/Truncated/);const bad=buffer.slice(0);new DataView(bad).setUint16(12,0x8001);assert.throws(()=>c.MidiPlayer.parse(bad),/PPQ/);
c.RichMedia=c.window.RichMedia;
const raw='\ue200image_group\ue202{"query":["sample image"],"layout":"carousel"}\ue201';const extracted=c.window.SavedWidgets.extract(raw);assert.equal(extracted.widgets[0].image_group.query[0],'sample image');assert(!extracted.text.includes('image_group'));
assert.equal(c.window.SavedWidgets.extract('```\n'+raw+'\n```').widgets.length,0);
const markup='<caption>A caption</caption> <text size="xs"><Link url="https://example.com/image" title="Image source"/></text>';const clean=c.window.RichMedia.markup(markup);assert(clean.includes('A caption'));assert(clean.includes('[Image source](<https://example.com/image>)'));assert(!clean.includes('<caption>'));assert.equal(c.window.RichMedia.markup('`'+markup+'`'),'`'+markup+'`');
console.log('Rich media: MIDI note timing, invalid/truncated/SMPTE handling, image_group extraction, captions/links and literal code preservation passed.');

const entity='<Entity category="book" value="Example title"/>';
assert(c.window.RichMedia.markup(entity).includes('Example title'));
assert(!c.window.RichMedia.markup(entity).includes('<Entity'));
assert.equal(c.window.RichMedia.markup('`'+entity+'`'),'`'+entity+'`');
assert.equal(c.window.RichMedia.markup('<Cite refs={["first","second"]}/>'),'\ue200cite\ue202first\ue202second\ue201');
assert.equal(c.window.RichMedia.markup('<Cite ref="first"/>'),'\ue200cite\ue202first\ue201');
assert(c.window.RichMedia.markup('<Link title="Example" url="https://example.com/a?b=1&amp;c=2"/>').includes('https://example.com/a?b=1&c=2'));
const series='## First\n'+raw+'\n\nFirst note.\n\n## Second\n'+raw+'\n\nFinal note.';
c.RichMedia=c.window.RichMedia;
const combined=c.window.SavedWidgets.extract(series),collection=combined.widgets.find(x=>x.image_group?.sections);
assert.equal(collection.image_group.sections.length,2);assert.equal(collection.image_group.sections[0].title,'First');assert.equal(collection.image_group.sections[0].description,'First note.');
assert.equal((combined.text.match(/OFFLINEWIDGETPLACEHOLDER/g)||[]).length,1);assert.equal(collection.image_group.sections[1].description,'Final note.');
assert.equal(c.window.SavedWidgets.extract('![legacy](local.png)').text,'![legacy](local.png)');
for(const [count,expected] of [[1,1],[2,2],[3,3],[4,2],[6,3],[9,3]])assert.equal(c.window.RichMedia.columns(count),expected);
console.log('New markup: visible entity labels, Cite refs, attribute order, unified image sections, quantity-based grids, legacy images and code preservation passed.');
const jsx='<grid columns={2}><grid-item><AsyncImage ref="saved0" aspectRatio="3:4"/>\n**First image**\n<caption>First caption.</caption></grid-item><grid-item><AsyncImage src="attachments/One.png"/>\n**Second image**</grid-item></grid>';
const converted=c.window.SavedWidgets.extract(c.window.RichMedia.markup(c.window.RichMedia.blocks('## One\n\n'+jsx+'\n\n<Link url="https://example.com/source" title="Source"/>\n\n## Two\n\n'+jsx+'\n\nSecond note.\n\nTrailing paragraph.')));
const sections=converted.widgets.find(x=>x.image_group?.sections).image_group.sections;
assert.equal(sections.length,2);assert.equal(sections[0].images.length,2);assert.equal(sections[0].images[0].title,'First image');assert.equal(sections[0].images[0].description,'First caption.');assert.equal(sections[0].images[0].ref,'saved0');assert.equal(sections[0].images[1].src,'attachments/One.png');assert(sections[0].description.includes('[Source](<https://example.com/source>)'));assert(converted.text.includes('Trailing paragraph.'));
assert.equal(c.window.RichMedia.blocks('```jsx\n'+jsx+'\n```'),'```jsx\n'+jsx+'\n```');
assert.equal(c.window.SavedWidgets.extract('## Single\n\n<AsyncImage ref="saved0"/>\n\n**Single caption**').widgets[0].image_group.images[0].title,'Single caption');
console.log('Structured JSX: grid items, AsyncImage refs and paths, labels, captions, source links, trailing prose and fenced examples passed.');

assert.equal(c.window.RichMedia.blocks('```jsx\n'+jsx),'```jsx\n'+jsx);
