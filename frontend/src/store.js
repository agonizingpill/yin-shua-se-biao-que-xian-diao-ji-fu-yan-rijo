import {api} from './api.js';
export const store={user:null,jobs:[],proofs:[],adjustments:[],plates:[],samples:[],holds:[],paperLots:[],paperIssues:[],machines:[],inspections:[],packs:[],shipments:[],blind:[],blindSummary:null,myBlind:[],proofId:null,adjustmentId:null};
export async function refresh(){[store.jobs,store.proofs,store.adjustments,store.plates,store.samples,store.holds,store.paperLots,store.paperIssues,store.machines,store.inspections,store.packs,store.shipments]=await Promise.all([api('/jobs'),api('/proofs'),api('/adjustments'),api('/plates'),api('/press-samples'),api('/press-holds'),api('/paper-lots'),api('/paper-issues'),api('/press-machines'),api('/press-inspections'),api('/print-packs'),api('/print-shipments')]);if(store.user?.role==='admin')[store.blind,store.blindSummary]=await Promise.all([api('/blind-samples'),api('/blind-samples/summary')]);if(!store.proofId&&store.proofs.length)store.proofId=store.proofs[0].id;if(!store.adjustmentId&&store.adjustments.length)store.adjustmentId=store.adjustments.at(-1).id;return store}
// 盲评员与车间数据隔离：仅拉取匿名留样，不请求任何工单、色标或机判接口。
export async function refreshBlind(){store.myBlind=await api('/blind/my-samples');return store}
export const proof=s=>s.proofs.find(x=>x.id===Number(s.proofId));
export const adjustment=s=>s.adjustments.find(x=>x.id===Number(s.adjustmentId));
