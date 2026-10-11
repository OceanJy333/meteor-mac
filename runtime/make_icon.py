# input: output png path; output: 1024px app icon (night sky, red butterfly, upright sword, meteor streak); pos: build-time asset generator for build.sh.
# Drawn from scratch so the release ships no game artwork.
import math,sys
from PIL import Image,ImageDraw,ImageFilter
S=1024;M=100;R=185  # macOS icon grid: 824px squircle-ish body inside a 1024 canvas
def body_mask():
 m=Image.new('L',(S,S),0);ImageDraw.Draw(m).rounded_rectangle((M,M,S-M,S-M),R,fill=255);return m
def sky():
 im=Image.new('RGB',(S,S));px=im.load()
 for y in range(S):
  for x in range(S):
   d=math.hypot(x-S*0.5,y-S*0.38)/(S*0.75);t=min(1,d)
   px[x,y]=(int(42-30*t),int(36-26*t),int(92-64*t))
 return im
def butterfly(cx,cy,k):
 # One symmetric loop of r = e^cos(t) - 2cos(4t): big upper wings, smaller lower wings.
 pts=[]
 for i in range(720):
  t=i/720*2*math.pi;r=math.exp(math.cos(t))-2*math.cos(4*t)
  pts.append((cx+k*abs(r)*math.sin(t),cy-k*abs(r)*math.cos(t)*0.92))
 return pts
def main(out):
 im=sky().convert('RGBA');d=ImageDraw.Draw(im)
 # meteor streak
 streak=Image.new('RGBA',(S,S),(0,0,0,0));sd=ImageDraw.Draw(streak)
 for i in range(80):
  a=i/80;sd.line((170+a*230,190+a*120,176+a*230,193+a*120),fill=(255,240,210,int(255*a)),width=int(2+12*a))
 sd.ellipse((392,300,424,330),fill=(255,250,235,255))
 im.alpha_composite(streak.filter(ImageFilter.GaussianBlur(3)))
 # glow + butterfly
 glow=Image.new('RGBA',(S,S),(0,0,0,0));ImageDraw.Draw(glow).polygon(butterfly(S/2,S*0.52,86),fill=(255,40,40,150))
 im.alpha_composite(glow.filter(ImageFilter.GaussianBlur(28)))
 d.polygon(butterfly(S/2,S*0.52,82),fill=(196,24,36,255))
 # sword: blade, guard, grip, pommel
 x=S/2;d.polygon([(x,190),(x+20,250),(x+20,700),(x-20,700),(x-20,250)],fill=(214,222,236,255))
 d.polygon([(x,190),(x+20,250),(x+20,700),(x,700)],fill=(160,172,196,255))
 d.rounded_rectangle((x-92,700,x+92,728),12,fill=(212,170,72,255))
 d.rounded_rectangle((x-17,728,x+17,850),8,fill=(70,40,30,255))
 d.ellipse((x-28,842,x+28,898),fill=(212,170,72,255))
 icon=Image.new('RGBA',(S,S),(0,0,0,0));icon.paste(im,(0,0),body_mask())
 shadow=Image.new('RGBA',(S,S),(0,0,0,0));shadow.paste((0,0,0,110),(0,12),body_mask())
 Image.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)),icon).save(out)
if __name__=='__main__':main(sys.argv[1])
