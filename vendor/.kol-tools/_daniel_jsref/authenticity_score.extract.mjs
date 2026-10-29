// 自动抽取自 .kol-tools/_daniel_bundle/authenticityScore-a-IZvxEl.pretty.js（逐字抽取，未改语义）
// 抽取范围：const Q ／ const te ／ q() ／ Y() ／ ne() ／ V() ／ ve() ／ je()
// 用途：Authenticity 的 Node 正控标尺（Python 端口见 .kol-tools/b10_authenticity.py）
const Q={
  mega:[27,18,5,1],macro:[32,10,1.3,.5],mid:[28,11,3.6,1.2],micro:[40,20,8,3],nano:[60,30,15,5]
};
const te={
  mega:1,macro:1,mid:2,micro:3,nano:5
};
function q(e){
  return e>=1e7?"mega":e>=1e6?"macro":e>=1e5?"mid":e>=1e4?"micro":"nano"
}
function Y(e,t){
  if(!e||e===0||t===0)return{
    ratio:0,percentileScore:50,isZombie:!1,tier:q(t)
  };
  const o=q(t),n=e/t*100,i=Q[o];
  let r;
  n>=i[0]?r=100:n>=i[1]?r=85:n>=i[2]?r=65:n>=i[3]?r=40:r=20;
  const s=t>=1e5&&n<te[o];
  return{
    ratio:n,percentileScore:r,isZombie:s,tier:o
  }
}
function ne(e,t){
  if(!e||e===0||t===0)return 50;
  const o=q(t),n=e/t*100;
  return o==="mega"||o==="macro"?n>=10?100:n>=5?85:n>=2?70:n>=1?45:n>=.5?25:n>=.1?10:0:o==="mid"?n>=15?100:n>=8?85:n>=3?70:n>=2?55:n>=1?35:n>=.5?20:5:n>=20?100:n>=10?85:n>=5?75:n>=2?60:40
}
function V(e,t,o,n,i,r,s,M={
  
}){
  const{
    inverted:l=!1,hardCeiling:f,hardFloor:p
  }=M;
  if(f!==void 0&&e>f||p!==void 0&&e<p)return 0;
  if(l){
    if(e>=n)return 100;
    if(e>=o)return 100-Math.round((n-e)/(n-o)*20);
    if(e>=t)return 80-Math.round((o-e)/(o-t)*30);
    const d=t-e,g=t*.8;
    return Math.max(0,g>0?50-Math.round(d/g*50):0)
  }else{
    if(e<=n)return 100;
    if(e<=i)return 100-Math.round((e-n)/(i-n)*20);
    if(e<=r)return 80-Math.round((e-i)/(r-i)*25);
    if(e<=s)return 55-Math.round((e-r)/(s-r)*25);
    const d=e-s,g=s*.5;
    return Math.max(0,30-Math.round(d/g*30))
  }
}
function ve(e){
  const{
    views:t,likes:o,comments:n,subscriberCount:i
  }=e;
  if(t.length<3)return{
    score:-1,label:"Insufficient Data",color:"text-muted-foreground",signals:[]
  };
  const r=[],s=t.reduce((a,m)=>a+m,0),M=o.reduce((a,m)=>a+m,0),l=n.reduce((a,m)=>a+m,0),f=s/t.length;
  let p;
  const d=i>0?f/i*100:0,g=l>0?s/l:99999;
  if(l===0)p=d>10?0:15,r.push({
    name:"View-Engagement Match",status:"fail",detail:`No comments with ${d.toFixed(1)}% View/Sub — highly suspicious`,rawScore:p
  });
  else{
    let a;
    i>=1e7?a=V(g,360,360,634,1127,2596,3429,{
      hardCeiling:15e3
    }):i>=2e6?a=V(g,382,382,612,1005,1830,2474,{
      hardCeiling:1e4
    }):i>=5e5?a=V(g,296,296,467,856,2115,4244,{
      hardCeiling:15e3
    }):i>=1e5?a=V(g,175,175,385,758,1680,2637,{
      hardCeiling:1e4
    }):a=V(g,144,144,265,539,1508,2020,{
      hardCeiling:8e3
    });
    let m=0;
    d>12&&a<100&&(d>65?m=Math.round((100-a)*.5):d>30?m=Math.round((100-a)*.35):m=Math.round((100-a)*.2)),p=Math.max(0,a-m);
    const E=p>=70?"pass":p>=40?"warn":"fail",_=p>=70?"(comments healthy)":p>=40?"(comments not scaling with views)":"(views inflated — comments far behind)",D=m>0?` [+${m}pt penalty: View/Sub ${d.toFixed(0)}%]`:"";
    r.push({
      name:"View-Engagement Match",status:E,detail:`${g.toFixed(0)} views/comment ${_}${D}`,rawScore:p
    })
  }const S=s>0?(M+l)/s*100:0;
  let h;
  i>=1e7?h=V(S,1.16,1.81,2.94,3.99,6.1,7.21,{
    inverted:!0,hardFloor:.1
  }):i>=2e6?h=V(S,1.24,1.91,3.02,4.64,7.54,8.74,{
    inverted:!0,hardFloor:.1
  }):i>=5e5?h=V(S,1.21,2.05,3.36,4.79,6.44,7.97,{
    inverted:!0,hardFloor:.1
  }):i>=1e5?h=V(S,.8,1.68,3.22,5.27,7.46,7.88,{
    inverted:!0,hardFloor:.1
  }):h=V(S,1.07,1.73,3.25,5.49,8.27,9.84,{
    inverted:!0,hardFloor:.1
  });
  const I=h>=70?"pass":h>=40?"warn":"fail";
  r.push({
    name:"Interact Rate",status:I,detail:`${S.toFixed(2)}% ${h>=70?"(healthy)":h>=40?"(low)":"(very low — suspicious)"}`,rawScore:h
  });
  const u=t.reduce((a,m)=>a+Math.pow(m-f,2),0)/t.length,c=f>0?Math.sqrt(u)/f:0;
  let b,y,L,A,k,x;
  i>=1e7?(y=.36,L=.47,A=.6,k=.87,x=1.13):i>=2e6?(y=.35,L=.47,A=.7,k=1.03,x=1.76):i>=5e5?(y=.39,L=.49,A=.76,k=1.12,x=1.79):i>=1e5?(y=.43,L=.58,A=.91,k=1.4,x=1.82):(y=.46,L=.67,A=1.02,k=1.44,x=1.86),c<.1?b=5:c<y?b=5+Math.round((c-.1)/(y-.1)*25):c<L?b=30+Math.round((c-y)/(L-y)*30):c<A?b=85+Math.round((A-c)/(A-L)*10):c<k?b=70+Math.round((k-c)/(k-A)*15):c<x?b=50+Math.round((x-c)/(x-k)*20):c<x*1.5?b=30+Math.round((x*1.5-c)/(x*.5)*20):b=Math.max(10,30-Math.round((c-x*1.5)/x*20));
  const N=b>=70?"pass":b>=40?"warn":"fail";
  r.push({
    name:"Fluctuation",status:N,detail:`CV ${c.toFixed(2)} ${b>=85?"(very stable)":b>=70?"(stable with bursts)":b>=50?"(volatile)":b>=30?"(too uniform or too volatile)":"(suspicious uniformity)"}`,rawScore:b
  });
  const $=Y(f,i),C=ne(f,i),B=$.ratio;
  let R;
  C>=85?R=`VPR ${B.toFixed(2)}% — excellent subscriber engagement`:C>=70?R=`VPR ${B.toFixed(2)}% — strong subscriber engagement`:C>=55?R=`VPR ${B.toFixed(2)}% — healthy subscriber engagement`:C>=40?R=`VPR ${B.toFixed(2)}% — moderate engagement`:C>=20?R=`VPR ${B.toFixed(2)}% — low views vs subscribers`:C>=5?R=`VPR ${B.toFixed(2)}% — very low views vs subscribers (likely zombie followers)`:R=`VPR ${B.toFixed(3)}% — nearly zero real viewership (zombie followers)`;
  const v=C>=70?"pass":C>=40?"warn":"fail";
  r.push({
    name:"Subscriber Engagement",status:v,detail:R,rawScore:C
  });
  let F;
  if(l===0&&M===0)F=20,r.push({
    name:"Like/Comment",status:"fail",detail:"No engagement",rawScore:F
  });
  else if(l===0)F=15,r.push({
    name:"Like/Comment",status:"fail",detail:"Likes but zero comments — suspicious",rawScore:F
  });
  else{
    const a=M/l;
    F=V(a,3.96,7.72,14.15,23.13,37.1,51.37,{
      hardCeiling:200
    });
    const m=F>=70?"pass":F>=40?"warn":"fail";
    r.push({
      name:"Like/Comment",status:m,detail:`${a.toFixed(1)}:1 ${F>=70?"(normal)":F>=40?"(borderline)":"(abnormal)"}`,rawScore:F
    })
  }const O=Math.max(0,Math.min(100,Math.round(p*.4+h*.2+b*.12+F*.08+C*.2)));
  let P,T;
  return O>=80?(P="Highly Authentic",T="text-emerald-600"):O>=60?(P="Normal",T="text-emerald-600"):O>=40?(P="Some Concerns",T="text-amber-600"):(P="Suspicious",T="text-red-500"),{
    score:O,label:P,color:T,signals:r
  }
}
function je(e,t){
  const o=(e??[]).filter(i=>Number(i.views??0)>=100).slice(0,50);
  return o.length<3?null:{
    ...ve({
      views:o.map(i=>Number(i.views??0)),likes:o.map(i=>Number(i.likes??0)),comments:o.map(i=>Number(i.comments??0)),subscriberCount:Math.max(0,t||0)
    }),sampleSize:o.length,samplePolicy:"latest_50_min_100_views"
  }
}

export { je as authenticityFromVideos, ve as authenticityFromArrays, V as scoreFromThresholds, Y as vprPercentile, ne as subscriberEngagement };
