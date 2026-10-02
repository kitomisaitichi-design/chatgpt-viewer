'use strict';
// Preserve extremes and gaps without creating a DOM node for every data point.
globalThis.ChartMath=(()=>{
 const finite=v=>v!==null&&v!==undefined&&v!==''&&Number.isFinite(Number(v));
 function extent(values){let min=Infinity,max=-Infinity;for(const v of values)if(finite(v)){min=Math.min(min,Number(v));max=Math.max(max,Number(v));}return {min,max};}
 function samples(data,key,limit=1600){if(data.length<=limit)return Array.from({length:data.length},(_,i)=>i);const chosen=new Set([0,data.length-1]),bucket=Math.max(1,Math.ceil(data.length/(limit/4)));
  for(let start=0;start<data.length;start+=bucket){let low=-1,high=-1,gap=-1;for(let i=start;i<Math.min(data.length,start+bucket);i++){const value=data[i]?.[key];if(!finite(value)){if(gap<0)gap=i;continue;}if(low<0||Number(value)<Number(data[low][key]))low=i;if(high<0||Number(value)>Number(data[high][key]))high=i;}for(const i of [start,low,high,gap])if(i>=0)chosen.add(i);}
  return [...chosen].sort((a,b)=>a-b);
 }
 function nearest(sorted,value){let low=0,high=sorted.length;while(low<high){const mid=(low+high)>>>1;if(sorted[mid]<value)low=mid+1;else high=mid;}if(!low)return 0;if(low===sorted.length)return low-1;return value-sorted[low-1]<=sorted[low]-value?low-1:low;}
 return {finite,extent,samples,nearest};
})();
