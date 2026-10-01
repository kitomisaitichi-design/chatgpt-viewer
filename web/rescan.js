'use strict';
window.RescanSchedule={
 minutes:[5,15,30,60,180,360,720,1440,4320],labels:['5 minutes','15 minutes','30 minutes','1 hour','3 hours','6 hours','12 hours','24 hours','3 days'],
 index(value){const found=this.minutes.indexOf(Number(value));return found<0?3:found;},
 interval(value){return this.minutes[this.index(value)]*60000;},
 due(settings,scan,now,next){return settings.autoRefresh===true&&!settings.scanPaused&&!scan?.scanning&&!!settings.scan_start&&now>=next;}
};
