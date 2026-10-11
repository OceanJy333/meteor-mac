// input: Direct3D 6 device state, FVF vertices and 16-bit surfaces from guest memory; output: macOS OpenGL draws; pos: native D3D6 backend.
#define GL_SILENCE_DEPRECATION
#include <OpenGL/gl.h>
#include <OpenGL/glext.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

static uint32_t rs[256];
static uint32_t tss[2][32];
static GLuint bound[2],white,scratch;
static int fbw=640,fbh=480;
static float world[16],view[16],proj[16];
static int vpx,vpy,vpw=640,vph=480;static float vpminz=0,vpmaxz=1;
// The game renders in fbw×fbh; the Retina drawable shows it in the letterboxed pixel rect gx,gy,gw,gh (bottom-left origin).
static int dwp=640,dhp=480,gx,gy,gw=640,gh=480;
static void map_rect(int x,int y,int w,int h,int scissor){
 int X=gx+(int)lround((double)x*gw/fbw),Y=gy+(int)lround((double)(fbh-y-h)*gh/fbh),X2=gx+(int)lround((double)(x+w)*gw/fbw),Y2=gy+(int)lround((double)(fbh-y)*gh/fbh);
 if(scissor)glScissor(X,Y,X2-X,Y2-Y);else glViewport(X,Y,X2-X,Y2-Y);
}
void gl_mode(int w,int h){fbw=w;fbh=h;}
void gl_drawable(const int *o){
 dwp=o[0];dhp=o[1];gx=o[2];gy=o[3];gw=o[4];gh=o[5];
 if(gx>0||gy>0){glEnable(GL_SCISSOR_TEST);glClearColor(0,0,0,1);
  if(gx>0){glScissor(0,0,gx,dhp);glClear(GL_COLOR_BUFFER_BIT);glScissor(gx+gw,0,dwp-gx-gw,dhp);glClear(GL_COLOR_BUFFER_BIT);}
  if(gy>0){glScissor(0,0,dwp,gy);glClear(GL_COLOR_BUFFER_BIT);glScissor(0,gy+gh,dwp,dhp-gy-gh);glClear(GL_COLOR_BUFFER_BIT);}
  glDisable(GL_SCISSOR_TEST);}
}
static uint8_t *vbuf;static size_t vcap;static int enhance;
typedef struct{int on,type;float color[4],pos[3],dir[3],range,att[3],theta,phi;}Light;
static Light lights[8];static float centre[3];static float mat[17]={1,1,1,1, 1,1,1,1, 0,0,0,0, 0,0,0,0, 0};static uint32_t ambient;
void gl_light(int i,int on,int type,const float *color,const float *pos,const float *dir,float range,float a0,float a1,float a2,float theta,float phi){
 if(i<0||i>=8)return;Light *l=&lights[i];l->on=on;l->type=type;memcpy(l->color,color,16);memcpy(l->pos,pos,12);memcpy(l->dir,dir,12);l->range=range;l->att[0]=a0;l->att[1]=a1;l->att[2]=a2;l->theta=theta;l->phi=phi;
}
void gl_material(const float *m){memcpy(mat,m,68);}
void gl_ambient(uint32_t c){ambient=c;}
static void lighting(int lit){
 if(!lit){glDisable(GL_LIGHTING);return;}
 glEnable(GL_LIGHTING);glMatrixMode(GL_MODELVIEW);glLoadMatrixf(view);
 float amb[4]={((ambient>>16)&255)/255.f,((ambient>>8)&255)/255.f,(ambient&255)/255.f,1};glLightModelfv(GL_LIGHT_MODEL_AMBIENT,amb);
 glLightModeli(GL_LIGHT_MODEL_COLOR_CONTROL,GL_SEPARATE_SPECULAR_COLOR);
 glMaterialfv(GL_FRONT_AND_BACK,GL_DIFFUSE,mat);glMaterialfv(GL_FRONT_AND_BACK,GL_AMBIENT,mat+4);
 float none[4]={0,0,0,1};glMaterialfv(GL_FRONT_AND_BACK,GL_SPECULAR,rs[29]?mat+8:none);glMaterialfv(GL_FRONT_AND_BACK,GL_EMISSION,mat+12);glMaterialf(GL_FRONT_AND_BACK,GL_SHININESS,fminf(128,fmaxf(0,mat[16])));
 glDisable(GL_COLOR_MATERIAL);glEnable(GL_NORMALIZE);
 for(int i=0;i<8;i++){
  Light *l=&lights[i];GLenum L=GL_LIGHT0+i;
  if(!l->on){glDisable(L);continue;}
  glEnable(L);float zero[4]={0,0,0,1};glLightfv(L,GL_AMBIENT,zero);glLightfv(L,GL_DIFFUSE,l->color);glLightfv(L,GL_SPECULAR,l->color);
  if(l->type==3){float p[4]={-l->dir[0],-l->dir[1],-l->dir[2],0};glLightfv(L,GL_POSITION,p);glLightf(L,GL_SPOT_CUTOFF,180);glLightf(L,GL_CONSTANT_ATTENUATION,1);glLightf(L,GL_LINEAR_ATTENUATION,0);glLightf(L,GL_QUADRATIC_ATTENUATION,0);}
  else{float p[4]={l->pos[0],l->pos[1],l->pos[2],1};glLightfv(L,GL_POSITION,p);
   // DX5/6 D3DLIGHT2: attenuation runs on range-normalized distance d'=(range-d)/range and multiplies intensity
   // (a0 + a1*d' + a2*d'^2). Fixed-function GL can't express that, so it is evaluated once per draw at the mesh centre.
   float dx=l->pos[0]-centre[0],dy=l->pos[1]-centre[1],dz=l->pos[2]-centre[2],d=sqrtf(dx*dx+dy*dy+dz*dz);
   float n=l->range>0?(l->range-d)/l->range:1,a=l->att[0]+l->att[1]*n+l->att[2]*n*n;
   if(l->range>0&&d>l->range)a=0;if(!(l->att[0]>0||l->att[1]>0||l->att[2]>0))a=1;
   if(a<=0){glDisable(L);continue;}
   glLightf(L,GL_CONSTANT_ATTENUATION,1/a);glLightf(L,GL_LINEAR_ATTENUATION,0);glLightf(L,GL_QUADRATIC_ATTENUATION,0);
   if(l->type==2){glLightfv(L,GL_SPOT_DIRECTION,l->dir);glLightf(L,GL_SPOT_CUTOFF,fminf(90,l->phi*90/(float)M_PI));glLightf(L,GL_SPOT_EXPONENT,1);}else glLightf(L,GL_SPOT_CUTOFF,180);}
 }
}

static void ident(float *m){memset(m,0,64);m[0]=m[5]=m[10]=m[15]=1;}
void gl_reset(int w,int h){
 fbw=w;fbh=h;memset(rs,0,sizeof rs);memset(tss,0,sizeof tss);
 rs[7]=1;rs[14]=1;rs[19]=2;rs[20]=1;rs[22]=3;rs[23]=4;rs[25]=8;rs[9]=2;rs[8]=3;rs[137]=1;rs[141]=1;rs[136]=1;
 for(int s=0;s<2;s++){tss[s][1]=s?1:4;tss[s][2]=2;tss[s][3]=1;tss[s][4]=s?1:2;tss[s][5]=2;tss[s][6]=1;tss[s][11]=s;tss[s][12]=tss[s][13]=tss[s][14]=1;tss[s][16]=1;tss[s][17]=1;tss[s][18]=1;}
 ident(world);ident(view);ident(proj);vpx=vpy=0;vpw=w;vph=h;
 if(!white){uint32_t px=0xffffffff;glGenTextures(1,&white);glBindTexture(GL_TEXTURE_2D,white);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,1,1,0,GL_RGBA,GL_UNSIGNED_BYTE,&px);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glGenTextures(1,&scratch);}
 glViewport(0,0,dwp,dhp);glClearColor(0,0,0,1);glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
}
void gl_render_state(int s,uint32_t v){if(s>=0&&s<256)rs[s]=v;}
uint32_t gl_get_render_state(int s){return s>=0&&s<256?rs[s]:0;}
void gl_stage_state(int st,int s,uint32_t v){if(st>=0&&st<2&&s>=0&&s<32)tss[st][s]=v;}
uint32_t gl_get_stage_state(int st,int s){return st>=0&&st<2&&s>=0&&s<32?tss[st][s]:0;}
void gl_transform(int kind,const float *m){if(kind==1)memcpy(world,m,64);else if(kind==2)memcpy(view,m,64);else if(kind==3)memcpy(proj,m,64);}
void gl_get_transform(int kind,float *m){memcpy(m,kind==1?world:kind==2?view:proj,64);}
void gl_viewport(int x,int y,int w,int h,float mn,float mx){vpx=x;vpy=y;vpw=w;vph=h;vpminz=mn;vpmaxz=mx<=mn?1:mx;}
void gl_bind(int stage,GLuint id){if(stage>=0&&stage<2)bound[stage]=id;}

// fmt: 0 RGB565, 1 ARGB1555, 2 ARGB4444, 3 XRGB1555, 4 ARGB8888, 5 XRGB8888
static void to_rgba(uint8_t *o,const uint8_t *p,int fmt,int key,uint32_t lo,uint32_t hi){
 uint32_t v=fmt>=4?*(const uint32_t*)p:*(const uint16_t*)p;uint8_t r,g,b,a=255;
 switch(fmt){
 case 0:r=(v>>11)*255/31;g=((v>>5)&63)*255/63;b=(v&31)*255/31;break;
 case 1:case 3:r=((v>>10)&31)*255/31;g=((v>>5)&31)*255/31;b=(v&31)*255/31;if(fmt==1)a=(v&0x8000)?255:0;break;
 case 2:a=(v>>12)*17;r=((v>>8)&15)*17;g=((v>>4)&15)*17;b=(v&15)*17;break;
 default:b=v;g=v>>8;r=v>>16;a=fmt==4?v>>24:255;
 }
 if(key&&v>=lo&&v<=hi)a=0;
 o[0]=r;o[1]=g;o[2]=b;o[3]=a;
}
static uint8_t *conv(const uint8_t *px,int w,int h,int pitch,int fmt,int key,uint32_t lo,uint32_t hi){
 static uint8_t *buf;static size_t cap;size_t n=(size_t)w*h*4;if(n>cap){buf=realloc(buf,n);cap=n;}
 int bpp=fmt>=4?4:2;
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)to_rgba(buf+((size_t)y*w+x)*4,px+(size_t)y*pitch+x*bpp,fmt,key,lo,hi);
 return buf;
}
GLuint gl_texture(GLuint id,const uint8_t *px,int w,int h,int pitch,int fmt,int key,uint32_t lo,uint32_t hi){
 if(!id)glGenTextures(1,&id);
 glBindTexture(GL_TEXTURE_2D,id);glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,0);
 glTexParameteri(GL_TEXTURE_2D,GL_GENERATE_MIPMAP,GL_TRUE);
 glTexImage2D(GL_TEXTURE_2D,0,(fmt==0||fmt==3||fmt==5)&&!key?GL_RGB:GL_RGBA,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,conv(px,w,h,pitch,fmt,key,lo,hi));
 return id;
}
void gl_delete_texture(GLuint id){if(id)glDeleteTextures(1,&id);}

static GLenum blend(uint32_t v,int src){
 switch(v){case 1:return GL_ZERO;case 2:return GL_ONE;case 3:return GL_SRC_COLOR;case 4:return GL_ONE_MINUS_SRC_COLOR;case 5:return GL_SRC_ALPHA;case 6:return GL_ONE_MINUS_SRC_ALPHA;
 case 7:return GL_DST_ALPHA;case 8:return GL_ONE_MINUS_DST_ALPHA;case 9:return GL_DST_COLOR;case 10:return GL_ONE_MINUS_DST_COLOR;case 11:return GL_SRC_ALPHA_SATURATE;
 case 12:return src?GL_SRC_ALPHA:GL_ONE_MINUS_SRC_ALPHA;case 13:return src?GL_ONE_MINUS_SRC_ALPHA:GL_SRC_ALPHA;}
 return src?GL_ONE:GL_ZERO;
}
static GLenum cmp(uint32_t v){static const GLenum t[]={GL_ALWAYS,GL_NEVER,GL_LESS,GL_EQUAL,GL_LEQUAL,GL_GREATER,GL_NOTEQUAL,GL_GEQUAL,GL_ALWAYS};return v<9?t[v]:GL_ALWAYS;}
static void arg(GLenum src,GLenum op,uint32_t a,int alpha,int stage){
 GLenum s=GL_TEXTURE;
 switch(a&15){case 0:case 4:s=GL_PRIMARY_COLOR;break;case 1:s=stage?GL_PREVIOUS:GL_PRIMARY_COLOR;break;case 3:s=GL_CONSTANT;break;}
 glTexEnvi(GL_TEXTURE_ENV,src,s);
 int comp=a&0x10,rep=(a&0x20)||alpha;
 glTexEnvi(GL_TEXTURE_ENV,op,rep?(comp?GL_ONE_MINUS_SRC_ALPHA:GL_SRC_ALPHA):(comp?GL_ONE_MINUS_SRC_COLOR:GL_SRC_COLOR));
}
static void combine(int stage,int alpha,uint32_t op,uint32_t a1,uint32_t a2){
 GLenum mode=alpha?GL_COMBINE_ALPHA:GL_COMBINE_RGB,scale=alpha?GL_ALPHA_SCALE:GL_RGB_SCALE;
 GLenum s0=alpha?GL_SOURCE0_ALPHA:GL_SOURCE0_RGB,s1=alpha?GL_SOURCE1_ALPHA:GL_SOURCE1_RGB,s2=alpha?GL_SOURCE2_ALPHA:GL_SOURCE2_RGB;
 GLenum o0=alpha?GL_OPERAND0_ALPHA:GL_OPERAND0_RGB,o1=alpha?GL_OPERAND1_ALPHA:GL_OPERAND1_RGB,o2=alpha?GL_OPERAND2_ALPHA:GL_OPERAND2_RGB;
 GLenum m=GL_MODULATE;float sc=1;
 switch(op){case 2:m=GL_REPLACE;break;case 3:m=GL_REPLACE;a1=a2;break;case 5:sc=2;break;case 6:sc=4;break;case 7:case 11:m=GL_ADD;break;case 8:m=GL_ADD_SIGNED;break;case 9:m=GL_ADD_SIGNED;sc=2;break;case 10:m=GL_SUBTRACT;break;
 case 12:case 13:case 14:case 15:case 16:m=GL_INTERPOLATE;break;}
 glTexEnvi(GL_TEXTURE_ENV,mode,m);glTexEnvf(GL_TEXTURE_ENV,scale,sc);
 arg(s0,o0,a1,alpha,stage);arg(s1,o1,a2,alpha,stage);
 if(m==GL_INTERPOLATE){
  GLenum src=op==12?GL_PRIMARY_COLOR:op==14?GL_CONSTANT:op==16?GL_PREVIOUS:GL_TEXTURE;
  glTexEnvi(GL_TEXTURE_ENV,s2,src);glTexEnvi(GL_TEXTURE_ENV,o2,GL_SRC_ALPHA);
 }
}
static void stages(void){
 float tf[4]={((rs[60]>>16)&255)/255.f,((rs[60]>>8)&255)/255.f,(rs[60]&255)/255.f,(rs[60]>>24)/255.f};
 int on=1;
 for(int s=0;s<2;s++){
  glActiveTexture(GL_TEXTURE0+s);
  if(!on||tss[s][1]==1){glDisable(GL_TEXTURE_2D);on=0;continue;}
  glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,bound[s]?bound[s]:white);
  int mag=tss[s][16]==1?GL_NEAREST:GL_LINEAR,mip=tss[s][18],min=tss[s][17]==1?(mip==3?GL_NEAREST_MIPMAP_LINEAR:mip==2?GL_NEAREST_MIPMAP_NEAREST:GL_NEAREST):(mip==3?GL_LINEAR_MIPMAP_LINEAR:mip==2?GL_LINEAR_MIPMAP_NEAREST:GL_LINEAR);
  // 3D surfaces get trilinear + anisotropic filtering at Retina scale; screen-space UI keeps the game's own filters.
  if(enhance&&mag==GL_LINEAR&&bound[s]){min=GL_LINEAR_MIPMAP_LINEAR;glTexParameterf(GL_TEXTURE_2D,GL_TEXTURE_MAX_ANISOTROPY_EXT,8);}
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,mag);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,min);
  GLenum wrap[]={GL_REPEAT,GL_REPEAT,GL_MIRRORED_REPEAT,GL_CLAMP_TO_EDGE,GL_CLAMP_TO_BORDER};
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,wrap[tss[s][13]<5?tss[s][13]:1]);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,wrap[tss[s][14]<5?tss[s][14]:1]);
  glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_COMBINE);glTexEnvfv(GL_TEXTURE_ENV,GL_TEXTURE_ENV_COLOR,tf);
  combine(s,0,tss[s][1],tss[s][2],tss[s][3]);
  combine(s,1,tss[s][4]==1?2:tss[s][4],tss[s][4]==1?1:tss[s][5],tss[s][6]);
 }
 glActiveTexture(GL_TEXTURE0);
}
static void apply(int rhw,int lit){
 if(rs[7])glEnable(GL_DEPTH_TEST);else glDisable(GL_DEPTH_TEST);
 glDepthMask(rs[14]?GL_TRUE:GL_FALSE);glDepthFunc(cmp(rs[23]));
 if(rs[27]){glEnable(GL_BLEND);glBlendFunc(blend(rs[19],1),blend(rs[20],0));}else glDisable(GL_BLEND);
 if(rs[15]||rs[41]){glEnable(GL_ALPHA_TEST);if(rs[15])glAlphaFunc(cmp(rs[25]),(rs[24]&255)/255.f);else glAlphaFunc(GL_GREATER,0);}else glDisable(GL_ALPHA_TEST);
 if(rs[22]==1)glDisable(GL_CULL_FACE);else{glEnable(GL_CULL_FACE);glCullFace(GL_BACK);glFrontFace(rs[22]==3?GL_CW:GL_CCW);}
 glShadeModel(rs[9]==1?GL_FLAT:GL_SMOOTH);
 glPolygonMode(GL_FRONT_AND_BACK,rs[8]==1?GL_POINT:rs[8]==2?GL_LINE:GL_FILL);
 if(rs[29]){glEnable(GL_COLOR_SUM);}else glDisable(GL_COLOR_SUM);
 if(rs[28]){
  float c[4]={((rs[34]>>16)&255)/255.f,((rs[34]>>8)&255)/255.f,(rs[34]&255)/255.f,1};glEnable(GL_FOG);glFogfv(GL_FOG_COLOR,c);
  float st,en,de;memcpy(&st,&rs[36],4);memcpy(&en,&rs[37],4);memcpy(&de,&rs[38],4);
  if(rs[35]==0){glFogi(GL_FOG_MODE,GL_LINEAR);glFogf(GL_FOG_START,0);glFogf(GL_FOG_END,1);}
  else{glFogi(GL_FOG_MODE,rs[35]==1?GL_EXP:rs[35]==2?GL_EXP2:GL_LINEAR);glFogf(GL_FOG_START,st);glFogf(GL_FOG_END,en);glFogf(GL_FOG_DENSITY,de);}
  glFogi(GL_FOG_COORDINATE_SOURCE,GL_FOG_COORDINATE);
 }else glDisable(GL_FOG);
 glDisable(GL_SCISSOR_TEST);
 enhance=!rhw;stages();
 if(rhw){
  map_rect(0,0,fbw,fbh,0);glDepthRange(0,1);
  float m[16]={2.f/fbw,0,0,0, 0,-2.f/fbh,0,0, 0,0,2,0, -1,1,-1,1};
  glMatrixMode(GL_PROJECTION);glLoadMatrixf(m);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 }else{
  map_rect(vpx,vpy,vpw,vph,0);glDepthRange(vpminz,vpmaxz);
  glMatrixMode(GL_PROJECTION);glLoadIdentity();glTranslatef(0,0,-1);glScalef(1,1,2);glMultMatrixf(proj);
  lighting(lit);glMatrixMode(GL_MODELVIEW);glLoadMatrixf(view);glMultMatrixf(world);
 }
 if(rhw)lighting(0);
}
// Output vertex: pos[4] rgba spec fog uv0[2] uv1[2] normal[3] = 68 bytes
#define OV 68
static size_t fvf_size(uint32_t f,int *ntex){
 size_t s=0;switch(f&0xe){case 2:s=12;break;case 4:s=16;break;case 6:s=16;break;case 8:s=20;break;case 0xa:s=24;break;case 0xc:s=28;break;case 0xe:s=32;break;}
 if(f&0x10)s+=12;if(f&0x20)s+=4;if(f&0x40)s+=4;if(f&0x80)s+=4;*ntex=(f>>8)&15;return s+*ntex*8;
}
int gl_draw(int prim,uint32_t fvf,const uint8_t *v,int count,const uint16_t *idx,int icount,int flags){
 int ntex;size_t stride=fvf_size(fvf,&ntex);int rhw=(fvf&0xe)==4;
 if(count<=0)return 0;
 if((size_t)count*OV>vcap){vcap=(size_t)count*OV*2;vbuf=realloc(vbuf,vcap);}
 int foglegacy=rs[28]&&rs[35]==0;
 for(int i=0;i<count;i++){
  const uint8_t *p=v+(size_t)i*stride;float *o=(float*)(vbuf+(size_t)i*OV);const float *pf=(const float*)p;
  size_t off=(fvf&0xe)==2?12:(fvf&0xe)==4?16:12+((((fvf&0xe)-4)/2)*4);
  if(rhw){float w=pf[3]>0?1.f/pf[3]:1.f;o[0]=pf[0]*w;o[1]=pf[1]*w;o[2]=pf[2]*w;o[3]=w;}
  else{o[0]=pf[0];o[1]=pf[1];o[2]=pf[2];o[3]=1;}
  if(fvf&0x10){memcpy(&o[11],p+off,12);off+=12;}else{o[11]=0;o[12]=0;o[13]=1;}if(fvf&0x20)off+=4;
  uint8_t *col=(uint8_t*)&o[4],*spec=(uint8_t*)&o[5];
  if(fvf&0x40){uint32_t c=*(const uint32_t*)(p+off);off+=4;col[0]=c>>16;col[1]=c>>8;col[2]=c;col[3]=c>>24;}else{col[0]=col[1]=col[2]=col[3]=255;}
  uint32_t sc=0xff000000;if(fvf&0x80){sc=*(const uint32_t*)(p+off);off+=4;}
  spec[0]=sc>>16;spec[1]=sc>>8;spec[2]=sc;spec[3]=0;
  o[6]=foglegacy?1.f-(sc>>24)/255.f:(rhw?o[3]:0);
  const float *t=(const float*)(p+off);
  for(int s=0;s<2;s++){int ti=tss[s][11]&7;if(ti<ntex){o[7+s*2]=t[ti*2];o[8+s*2]=t[ti*2+1];}else{o[7+s*2]=o[8+s*2]=0;}}
 }
 int lit=!rhw&&(fvf&0x10)&&!(flags&0x10);
 if(lit){float c[3]={0,0,0};for(int i=0;i<count;i++){const float *o=(const float*)(vbuf+(size_t)i*OV);c[0]+=o[0];c[1]+=o[1];c[2]+=o[2];}
  for(int k=0;k<3;k++)c[k]/=count;for(int k=0;k<3;k++)centre[k]=c[0]*world[k]+c[1]*world[4+k]+c[2]*world[8+k]+world[12+k];}
 apply(rhw,lit);
 if(lit){glEnableClientState(GL_NORMAL_ARRAY);glNormalPointer(GL_FLOAT,OV,vbuf+44);}else glDisableClientState(GL_NORMAL_ARRAY);
 glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(4,GL_FLOAT,OV,vbuf);
 glEnableClientState(GL_COLOR_ARRAY);glColorPointer(4,GL_UNSIGNED_BYTE,OV,vbuf+16);
 glEnableClientState(GL_SECONDARY_COLOR_ARRAY);glSecondaryColorPointer(3,GL_UNSIGNED_BYTE,OV,vbuf+20);
 glEnableClientState(GL_FOG_COORDINATE_ARRAY);glFogCoordPointer(GL_FLOAT,OV,vbuf+24);
 for(int s=0;s<2;s++){glClientActiveTexture(GL_TEXTURE0+s);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glTexCoordPointer(2,GL_FLOAT,OV,vbuf+28+s*8);}
 glClientActiveTexture(GL_TEXTURE0);
 static const GLenum modes[]={GL_POINTS,GL_POINTS,GL_LINES,GL_LINE_STRIP,GL_TRIANGLES,GL_TRIANGLE_STRIP,GL_TRIANGLE_FAN};
 GLenum mode=prim>0&&prim<7?modes[prim]:GL_TRIANGLES;
 if(idx)glDrawElements(mode,icount,GL_UNSIGNED_SHORT,idx);else glDrawArrays(mode,0,count);
 return glGetError();
}
void gl_clear(int x,int y,int w,int h,int flags,uint32_t color,float z){
 glEnable(GL_SCISSOR_TEST);map_rect(x,y,w,h,1);
 glClearColor(((color>>16)&255)/255.f,((color>>8)&255)/255.f,(color&255)/255.f,(color>>24)/255.f);glClearDepth(z);
 glDepthMask(GL_TRUE);glColorMask(1,1,1,1);
 glClear((flags&1?GL_COLOR_BUFFER_BIT:0)|(flags&2?GL_DEPTH_BUFFER_BIT:0)|(flags&4?GL_STENCIL_BUFFER_BIT:0));
 glDisable(GL_SCISSOR_TEST);
}
// 2D image draw into the framebuffer (system-memory surface → render target).
void gl_blit(const uint8_t *px,int pitch,int fmt,int sx,int sy,int sw,int sh,int dx,int dy,int dw,int dh,int key,uint32_t lo,uint32_t hi){
 if(sw<=0||sh<=0||dw<=0||dh<=0)return;
 int bpp=fmt>=4?4:2;
 glPushAttrib(GL_ALL_ATTRIB_BITS);
 for(int s=1;s>=0;s--){glActiveTexture(GL_TEXTURE0+s);glDisable(GL_TEXTURE_2D);}
 glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,scratch);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_REPLACE);
 glPixelStorei(GL_UNPACK_ALIGNMENT,1);
 glTexParameteri(GL_TEXTURE_2D,GL_GENERATE_MIPMAP,GL_FALSE);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,sw,sh,0,GL_RGBA,GL_UNSIGNED_BYTE,conv(px+(size_t)sy*pitch+sx*bpp,sw,sh,pitch,fmt,key,lo,hi));
 int scale=sw!=dw||sh!=dh;
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,scale?GL_LINEAR:GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,scale?GL_LINEAR:GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glDisable(GL_DEPTH_TEST);glDisable(GL_CULL_FACE);glDisable(GL_BLEND);glDisable(GL_FOG);glDisable(GL_COLOR_SUM);glDisable(GL_SCISSOR_TEST);
 if(key){glEnable(GL_ALPHA_TEST);glAlphaFunc(GL_GREATER,0);}else glDisable(GL_ALPHA_TEST);
 glPolygonMode(GL_FRONT_AND_BACK,GL_FILL);map_rect(0,0,fbw,fbh,0);
 glMatrixMode(GL_PROJECTION);glPushMatrix();glLoadIdentity();glOrtho(0,fbw,fbh,0,-1,1);
 glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadIdentity();
 glDisableClientState(GL_VERTEX_ARRAY);glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_SECONDARY_COLOR_ARRAY);glDisableClientState(GL_FOG_COORDINATE_ARRAY);
 for(int s=0;s<2;s++){glClientActiveTexture(GL_TEXTURE0+s);glDisableClientState(GL_TEXTURE_COORD_ARRAY);}
 glClientActiveTexture(GL_TEXTURE0);
 glColor4f(1,1,1,1);
 glBegin(GL_QUADS);glTexCoord2f(0,0);glVertex2i(dx,dy);glTexCoord2f(1,0);glVertex2i(dx+dw,dy);glTexCoord2f(1,1);glVertex2i(dx+dw,dy+dh);glTexCoord2f(0,1);glVertex2i(dx,dy+dh);glEnd();
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glMatrixMode(GL_MODELVIEW);glPopAttrib();
}
// Render target → 16-bit system copy (top-down rows), sampled from the scaled game rect.
void gl_readback(uint8_t *px,int pitch,int w,int h){
 static uint8_t *buf;static size_t cap;size_t n=(size_t)gw*gh*4;if(n>cap){buf=realloc(buf,n);cap=n;}
 glPixelStorei(GL_PACK_ALIGNMENT,1);glReadBuffer(GL_BACK);glReadPixels(gx,gy,gw,gh,GL_RGBA,GL_UNSIGNED_BYTE,buf);
 for(int y=0;y<h;y++){int sy=gh-1-(int)((y+.5)*gh/fbh);uint16_t *o=(uint16_t*)(px+(size_t)y*pitch);
  for(int x=0;x<w;x++){const uint8_t *c=buf+((size_t)sy*gw+(int)((x+.5)*gw/fbw))*4;o[x]=(c[0]>>3)<<11|(c[1]>>2)<<5|c[2]>>3;}}
}
// 16-bit software blit between system surfaces; key range skips source pixels.
void sw_blit(uint8_t *d,int dpitch,int dw,int dh,int dx,int dy,int dr,int db,const uint8_t *s,int spitch,int sw,int sh,int sx,int sy,int sr,int sb,int bpp,int key,uint32_t lo,uint32_t hi){
 if(dr<=dx||db<=dy||sr<=sx||sb<=sy)return;
 int same=(dr-dx)==(sr-sx)&&(db-dy)==(sb-sy);
 for(int y=dy<0?0:dy;y<db&&y<dh;y++){
  int b=same?sy+(y-dy):sy+(int)((int64_t)(y-dy)*(sb-sy)/(db-dy));if(b<0||b>=sh)continue;
  for(int x=dx<0?0:dx;x<dr&&x<dw;x++){
   int a=same?sx+(x-dx):sx+(int)((int64_t)(x-dx)*(sr-sx)/(dr-dx));if(a<0||a>=sw)continue;
   if(bpp==2){uint16_t c=*(const uint16_t*)(s+(size_t)b*spitch+a*2);if(key&&c>=lo&&c<=hi)continue;*(uint16_t*)(d+(size_t)y*dpitch+x*2)=c;}
   else{uint32_t c=*(const uint32_t*)(s+(size_t)b*spitch+a*4);if(key&&c>=lo&&c<=hi)continue;*(uint32_t*)(d+(size_t)y*dpitch+x*4)=c;}
  }
 }
}
void sw_fill(uint8_t *d,int pitch,int w,int h,int x0,int y0,int x1,int y1,int bpp,uint32_t c){
 for(int y=y0<0?0:y0;y<y1&&y<h;y++)for(int x=x0<0?0:x0;x<x1&&x<w;x++){if(bpp==2)*(uint16_t*)(d+(size_t)y*pitch+x*2)=c;else *(uint32_t*)(d+(size_t)y*pitch+x*4)=c;}
}
// GDI text: writes the pre-encoded color where the 8-bit coverage mask is >127.
void sw_text(uint8_t *d,int pitch,int w,int h,int bpp,const uint8_t *m,int mw,int mh,int x0,int y0,uint32_t c){
 for(int y=0;y<mh;y++){int ty=y0+y;if(ty<0||ty>=h)continue;
  for(int x=0;x<mw;x++){int tx=x0+x;if(tx<0||tx>=w||m[y*mw+x]<=127)continue;
   if(bpp==2)*(uint16_t*)(d+(size_t)ty*pitch+tx*2)=c;else *(uint32_t*)(d+(size_t)ty*pitch+tx*4)=c;}}
}
// Full-resolution RGBA capture of the displayed game rect (bottom-up rows) for verification snapshots.
int gl_grab(uint8_t *out,int cap,int *size){
 size[0]=gw;size[1]=gh;if((size_t)gw*gh*4>(size_t)cap)return 0;
 glPixelStorei(GL_PACK_ALIGNMENT,1);glReadBuffer(GL_BACK);glReadPixels(gx,gy,gw,gh,GL_RGBA,GL_UNSIGNED_BYTE,out);return 1;
}
