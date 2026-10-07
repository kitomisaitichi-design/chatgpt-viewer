const assert=require('assert'),fs=require('fs'),vm=require('vm'),path=require('path');
const context={};vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/document-cards.js'),'utf8'),context);const extract=context.DocumentCards.extract;
const source='Before\n:::writing{variant="document" id="123" title="A \\"quoted\\" title"}\n# Heading\n\nMath: \\(E=mc^2\\)\n\n| A | B |\n|---|---|\n| 1 | 2 |\n:::\nAfter';
// Baseline bundled Markdown parser leaves the writing directive literal.
const marked=require('../web/vendor/marked.js');assert(marked.parse(source).includes(':::writing'));
const result=extract(source);assert.equal(result.documents.length,1);assert.equal(result.documents[0].title,'A "quoted" title');assert(result.documents[0].body.includes('\\(E=mc^2\\)'));assert(result.text.includes('After'));assert(!result.text.includes(':::writing'));assert(marked.parse(result.text).includes('<table>'));
for(const fence of ['```','~~~~']){const literal=fence+'text\n:::writing{variant="document" title="Literal"}\n:::\n'+fence;assert.equal(extract(literal).documents.length,0);assert.equal(extract(literal).text,literal);}
assert.equal(extract(':::writing{variant="unknown" title="No"}\nText\n:::').documents.length,0);
assert.equal(extract(':::writing{variant="document" title="Partial"}\nStill loading').documents[0].body,'Still loading');
assert.equal(extract(':::writing{"variant":"document","title":"JSON"}\nText\n:::').documents[0].title,'JSON');
assert.equal(extract(':::writing{variant="document" title="One"}\nA\n:::\n:::writing{variant="document" title="Two"}\nB\n:::').documents.length,2);
assert.equal(extract(':::writing{variant="document" title=broken}\nText\n:::').documents.length,0);
console.log('Writing enclosures: original reproduction, math/table preservation, fences, partial, JSON and multiple cards passed.');
