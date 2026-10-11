// input: Unicorn engine + guest RAM base; output: native handling of hot IDirect3DDevice3 calls; pos: fast path beside d3dgl.c.
// A level frame issues ~600 render-state/texture/draw calls; doing them here instead of Python is the main frame-rate win.
// Any call that needs Python-side state (dirty textures, lights, legacy states) jumps to its Python stub instead.
#include <stdint.h>
#include <string.h>
#include <stdlib.h>
typedef struct uc_struct uc_engine;
typedef size_t uc_hook;
// Python loads libunicorn privately, so its entry points arrive as pointers from fast_install.
static int (*uc_hook_add)(uc_engine *uc,uc_hook *hh,int type,void *cb,void *user,uint64_t begin,uint64_t end,...);
static int (*uc_reg_read)(uc_engine *uc,int regid,void *value);
static int (*uc_reg_write)(uc_engine *uc,int regid,const void *value);
enum{REG_EAX=19,REG_EIP=26,REG_ESP=30,HOOK_CODE=4,SLOTS=4096,TEXES=8192};
void gl_render_state(int s,uint32_t v);uint32_t gl_get_render_state(int s);
void gl_stage_state(int st,int s,uint32_t v);uint32_t gl_get_stage_state(int st,int s);
void gl_transform(int kind,const float *m);void gl_get_transform(int kind,float *m);
void gl_bind(int stage,unsigned id);int gl_draw(int prim,uint32_t fvf,const uint8_t *v,int count,const uint16_t *idx,int icount,int flags);
static uint8_t *mem;static uint32_t lo;static uc_hook hh;
static uint8_t op[SLOTS];static uint32_t py[SLOTS];
static uint32_t textures[2];static int gate=1;static long draws;
static uint32_t tkey[TEXES],tval[TEXES];
static uint32_t *tex_slot(uint32_t p){uint32_t i=(p>>4)*2654435761u%TEXES;while(tkey[i]&&tkey[i]!=p)i=(i+1)%TEXES;return &tkey[i];}
void fast_tex_put(uint32_t p,uint32_t gl){uint32_t *k=tex_slot(p);*k=p;tval[k-tkey]=gl;}
void fast_tex_drop(uint32_t p){uint32_t *k=tex_slot(p);if(*k)tval[k-tkey]=0;}
static int tex_lookup(uint32_t p,uint32_t *gl){if(!p){*gl=0;return 1;}uint32_t *k=tex_slot(p);if(!*k||!tval[k-tkey])return 0;*gl=tval[k-tkey];return 1;}
void fast_gate(int closed){gate=closed;}
void fast_set_texture(int st,uint32_t p){if(st>=0&&st<2)textures[st]=p;}
uint32_t fast_texture(int st){return st>=0&&st<2?textures[st]:0;}
long fast_draws(void){return draws;}
void fast_stub(uint32_t slot,int which,uint32_t pyaddr){if(slot<SLOTS){op[slot]=which;py[slot]=pyaddr;}}
#define U32(a) (*(uint32_t*)(mem+(a)))
static int draw(uint32_t *a,int indexed){
 uint32_t t0,t1;if(gate||!tex_lookup(textures[0],&t0)||!tex_lookup(textures[1],&t1))return 0;
 gl_bind(0,t0);gl_bind(1,t1);
 if(indexed)gl_draw(a[1],a[2],mem+a[3],a[4],(const uint16_t*)(mem+a[5]),a[6],a[7]);
 else gl_draw(a[1],a[2],mem+a[3],a[4],0,0,a[5]);
 draws++;return 1;
}
static void hook(uc_engine *uc,uint64_t addr,uint32_t size,void *user){
 uint32_t slot=(uint32_t)(addr-lo)/16,esp,eax=0;int argc;uc_reg_read(uc,REG_ESP,&esp);
 uint32_t ret=U32(esp),*a=(uint32_t*)(mem+esp+4);
 switch(op[slot]){
  case 21:U32(a[2])=gl_get_render_state(a[1]);argc=3;break;
  case 22:if(a[1]==1||a[1]==21)goto python;gl_render_state(a[1],a[2]);argc=3;break;
  case 25:gl_transform(a[1],(float*)(mem+a[2]));argc=3;break;
  case 26:gl_get_transform(a[1],(float*)(mem+a[2]));argc=3;break;
  case 28:if(!draw(a,0))goto python;argc=6;break;
  case 29:if(!draw(a,1))goto python;argc=8;break;
  case 37:U32(a[2])=a[1]<2?textures[a[1]]:0;argc=3;break;
  case 38:if(a[1]<2)textures[a[1]]=a[2];argc=3;break;
  case 39:U32(a[3])=gl_get_stage_state(a[1],a[2]);argc=4;break;
  case 40:gl_stage_state(a[1],a[2],a[3]);argc=4;break;
  default:goto python;
 }
 esp+=4+4*argc;uc_reg_write(uc,REG_EAX,&eax);uc_reg_write(uc,REG_ESP,&esp);uc_reg_write(uc,REG_EIP,&ret);return;
 python:uc_reg_write(uc,REG_EIP,&py[slot]);
}
int fast_install(uc_engine *uc,uint8_t *base,uint32_t start,uint32_t end,void *hook_add,void *reg_read,void *reg_write){
 uc_hook_add=hook_add;uc_reg_read=reg_read;uc_reg_write=reg_write;mem=base;lo=start;return uc_hook_add(uc,&hh,HOOK_CODE,(void*)hook,0,start,end);
}
// Debug (METEOR_BLOCKS): per-4K-page count of executed guest blocks, to find code running outside the PE image.
static uint32_t *page_hits;static uc_hook bh;
static void block_hook(uc_engine *uc,uint64_t addr,uint32_t size,void *user){if(addr<0x60000000)page_hits[addr>>12]++;}
int fast_blocks(uc_engine *uc){
 page_hits=calloc(0x60000,4);
 return uc_hook_add(uc,&bh,8,(void*)block_hook,0,1,0);
}
uint32_t fast_block_hits(uint32_t page){return page_hits&&page<0x60000?page_hits[page]:0;}
