const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const context={window:{addEventListener(){}},URL,URLSearchParams,structuredClone};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/vendor/dagre.min.js'),'utf8'),context,{filename:'dagre.min.js'});
context.window.dagre=context.dagre;
for(const file of ['structured-content.js','rich-media.js','widgets.js']){
 vm.runInContext(fs.readFileSync(path.join(__dirname,'../web',file),'utf8'),context,{filename:file});
}
const parser=context.window.StructuredContent,extract=s=>context.window.SavedWidgets.extract(s);
const graph='flowchart TD A["Inherited allele, haplotype and regulatory configuration"] --> B["Neural, physiological and developmental response"] B --> C["Joint cognitive and temperament distribution"] C --> D["Threshold mass: L1 to L5 and other traits"] D --> E["Observed multi-domain production and behavior"] C --> G["Assortative mating and differential reproduction"] G --> H["Offspring genomic architecture"] H --> I["F1 and F2 developmental phenotype"] F --> I I --> J["Next-generation performance and reproduction"] J --> G J --> F';
let value=extract('The biological evidence fixes several links.\n\n'+graph+'\nNo disembodied variable is needed.\n\nSeveral measured results.');
assert.equal(value.widgets.length,1);
const d=value.widgets[0].diagram;
assert.equal(d.direction,'TD');
assert.equal(d.nodes.find(x=>x.id==='A').label,'Inherited allele, haplotype and regulatory configuration');
assert(d.edges.some(x=>x.from==='J'&&x.to==='F'));
assert(d.edges.some(x=>x.from==='D'&&x.to==='E'));
assert.equal(d.edges.length,11);
const feedback=parser.diagramModel(d);
assert(feedback.tiers.length>=6,'Feedback edges should not flatten the whole cycle into one row');
assert(feedback.height>feedback.position.get('C').y);
assert(feedback.links.every(e=>e.points.length>=2),'Every edge needs routed endpoints');
assert(value.text.includes('No disembodied variable is needed.'));
assert(!value.text.includes('flowchart TD'));
assert(!value.text.includes('OFFLINEWIDGETPLACEHOLDERNaN'));
for(const dir of ['TD','BT','LR','RL']){
 const changed=`flowchart ${dir}\n Alpha["A new arbitrary long node caption"] --> Beta["Second item"]\n Beta -.-> Gamma["Variable detail"]\n Gamma --> Alpha\n Gamma ==> Delta["Final output"]`;
 const chart=extract(changed).widgets[0].diagram,layout=parser.diagramModel(chart);
 assert.equal(chart.direction,dir);assert.equal(chart.nodes.length,4);assert.equal(chart.edges.length,4);
 assert(layout.width>0&&layout.height>0);
 assert.equal(layout.position.size,4);
 assert(layout.links.every(e=>e.points.length>=2));
 for(const box of layout.position.values())assert(box.x>=0&&box.y>=0&&box.x+box.width<=layout.width+1&&box.y+box.height<=layout.height+1);
}
const compact=extract('flowchart LR A-->B B-.->C C==>D D---A').widgets[0].diagram;
assert.equal(compact.edges.length,4);
assert(compact.edges.some(x=>x.from==='A'&&x.to==='B'));
assert(compact.edges.some(x=>x.from==='B'&&x.to==='C'&&x.type==='-.->'));
value=extract('See:\n\n```mermaid\nflowchart LR\nleft[Start] --> right[Finish]\n```\n\nNext paragraph');
assert.equal(value.widgets.length,1);assert.equal(value.widgets[0].diagram.direction,'LR');assert(value.text.includes('Next paragraph'));
value=extract('```md\nflowchart TD A --> B\n<Chart content={{"chartType":"line","series":[],"data":[]}}/>\n```');
assert.equal(value.widgets.length,0);
value=extract('Quoted `<Chart content={{"chartType":"line","series":[],"data":[]}}/>` is not visual.');
assert.equal(value.widgets.length,0);
const values=[{PCs:'2',cognitive:0.46966,technical:.34518,homicide:.17495},{PCs:'4',cognitive:.4204,technical:.30977,homicide:.230},{PCs:'20',cognitive:.42892,technical:.29616,homicide:.23551}];
const content={chartType:'line',meta:{title:'Cross-basis genomic distance correspondence',description:'New caption'},xKey:'PCs',series:[{dataKey:'cognitive',label:'Cognitive proxy'},{dataKey:'technical',label:'Technical proxy'},{dataKey:'homicide',label:'Homicide'}],yAxisMin:0,yAxisMax:.5,data:values};
value=extract('## 6. Dimensional changes\n\n<Chart content={'+JSON.stringify(content)+'}/>\n\nKernel-balanced correlations.');
assert.equal(value.widgets.length,1);
assert.equal(value.widgets[0].chart.data[1].technical,.30977);
assert.equal(value.widgets[0].chart.meta.title,'Cross-basis genomic distance correspondence');
assert(value.text.includes('Kernel-balanced correlations.'));
const newSeries={...content,xKey:'Epoch',data:[{Epoch:'A',cognitive:12,technical:-10,homicide:4},{Epoch:'B',cognitive:17,technical:-5,homicide:9}],yAxisMin:-12,yAxisMax:20};
assert.equal(extract('<Chart content={'+JSON.stringify(newSeries)+'}/>').widgets[0].chart.data[0].technical,-10);
assert.equal(extract('<Chart content={{"chartType":"line","data":[} />').widgets.length,0);
const metric='<grid columns={3}><grid-item><box border radius="lg" padding={3}><text size="xs" color="secondary">Genomic references</text><title size="lg">52</title><text size="sm">2,601 sampled genomes across seven reference spaces</text></box></grid-item><grid-item><box><text size="xs">Country output observations</text><title>28</title><caption>Original 5+5+5+5+5+3 sampling design</caption></box></grid-item><grid-item><box><text size="xs">Cognitive–technical correlation</text><title>0.918</title><text size="sm">Across the 28 constructed output coordinates</text></box></grid-item></grid>';
value=extract('Intro\n\n'+metric+'\n\nThe more revealing decomposition is:');
assert.equal(value.widgets.length,1);
const cards=value.widgets[0].layout;
assert.equal(cards.type,'grid');assert.equal(cards.attrs.columns,'3');assert.equal(cards.children.length,3);
assert.equal(cards.children[0].children[0].children[2].children[0],'2,601 sampled genomes across seven reference spaces');
assert(value.text.includes('The more revealing decomposition is:'));
// Reader must extract DIL before its normal markup stripping; <text size>
// conveys the small metric label and secondary caption.
const readerOrder=context.window.RichMedia.markup(extract(metric).text);
assert(!readerOrder.includes('<text'));
assert.equal(extract(metric).widgets[0].layout.children[0].children[0].children[0].attrs.size,'xs');
assert.equal(extract(metric).widgets[0].layout.children[0].children[0].children[2].attrs.size,'sm');
for(const n of [1,2,4,6]){
 const variable='<flow columns={'+n+'}>'+Array.from({length:n},(_,i)=>'<flow-item><box><text size="xs">Measure '+i+'</text><title>'+i*i+'</title><caption>Secondary line '+i+'</caption></box></flow-item>').join('')+'</flow>';
 assert.equal(extract(variable).widgets[0].layout.children.length,n);
}
value=extract('<table><table-row header={true}><table-cell header={true}>Population</table-cell><table-cell header={true}>Metric</table-cell></table-row><table-row><table-cell>Example</table-cell><table-cell>0.57</table-cell></table-row></table>');
assert.equal(value.widgets[0].layout.type,'table');assert.equal(value.widgets[0].layout.children.length,2);
assert.equal(extract('| Population | Score |\n|---|---|\n| Example | 2 |').widgets.length,0);
const documentA='<box flex="1" gap={1}>\n**[Population Architecture — Meta-Integrative Evidence Atlas](sandbox:/mnt/data/population_architecture_meta_integrative_evidence_atlas_2026.xlsx)**\n\n<text color="secondary" size="xs">19 sheets. Includes 52 genomic populations and 28 national-output records.</text>\n</box>';
const documentB='<box flex="1" gap={1}>\n**[Original 101-sheet expanded outcome workbook](sandbox:/mnt/data/28_population_all_metrics_28_rows_relative_poverty_2026.xlsx)**\n\n<text color="secondary" size="xs">Preserved source-level tables and normalized poverty dimensions.</text>\n</box>';
value=extract('Download the complete evidence atlas\n\n'+documentA+'\n\n'+documentB+'\n\nAfter these files.');
assert.equal(value.widgets.filter(w=>w.downloads).length,1,'Adjacent file boxes become a single collection');
assert.equal(value.widgets.find(w=>w.downloads).downloads.length,2);
assert.equal(value.widgets.find(w=>w.downloads).downloads[0].layout.children[1].attrs.size,'xs');
assert(value.text.includes('After these files.'));
const nestedLink=extract('<box><Link url="https://example.com/report.xlsx" title="Research sheet"/><caption>Details below.</caption></box>');
assert.equal(nestedLink.widgets[0].layout.children[0].attrs.title,'Research sheet');
console.log('Saved DIL charts, responsive metric cards/subtext, tables, evolving directional graphs and code exclusions passed.');
