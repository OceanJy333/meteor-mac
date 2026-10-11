// input: guest bitmap pixels; output: converted rectangle; pos: GDI color-format adapter.
#include <stdint.h>
static uint32_t read_pixel(const uint8_t *p,int b){if(b==16){unsigned v=*(const uint16_t*)p;return ((v>>11)*255/31)<<16|(((v>>5)&63)*255/63)<<8|(v&31)*255/31;}if(b>=24)return p[2]<<16|p[1]<<8|p[0];return *p*0x10101;}
void pixels_copy(uint8_t *dst,int dw,int dh,int db,int dx,int dy,const uint8_t *src,int sw,int sh,int sb,int sx,int sy,int width,int height,int flip,int packed_dst,int packed_src){
 int ds=packed_dst?dw*db/8:((dw*db+31)/32)*4,ss=packed_src?sw*sb/8:((sw*sb+31)/32)*4;
 for(int y=0;y<height;y++)for(int x=0;x<width;x++){
  int ax=dx+x,ay=dy+y,bx=sx+x,by=sy+y;if(ax<0||ay<0||ax>=dw||ay>=dh||bx<0||by<0||bx>=sw||by>=sh)continue;if(flip)by=sh-1-by;
  uint32_t c=read_pixel(src+by*ss+bx*(sb/8),sb);uint8_t *p=dst+ay*ds+ax*(db/8);
  if(db==16)*(uint16_t*)p=(((c>>16)&255)>>3)<<11|(((c>>8)&255)>>2)<<5|(c&255)>>3;
  else if(db>=24){p[0]=c;p[1]=c>>8;p[2]=c>>16;if(db==32)p[3]=255;}else *p=c;
 }
}
