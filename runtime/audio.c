// input: DirectSound buffers and waveOut headers living in guest RAM; output: mixed stereo audio on CoreAudio; pos: native sound backend.
// The game writes PCM into guest memory; the audio thread reads it in place, so Python only handles control calls.
#include <AudioToolbox/AudioToolbox.h>
#include <math.h>
#include <stdint.h>
#include <string.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
enum{VOICES=256,WAVEQ=64,RATE=44100};
typedef struct{int used,playing,loop,bits,channels;uint32_t data,bytes,rate;double pos;float gain,pan;const uint8_t *host;}Voice;
static uint8_t *mem;static AudioUnit unit;static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static Voice voices[VOICES];static float master=1;static FILE *dump; // METEOR_AUDIO_DUMP=path records raw float32 stereo for verification
// waveOut stream: queue of WAVEHDR guest pointers, played in order; dwFlags gets WHDR_DONE when consumed.
static uint32_t waveq[WAVEQ];static int qhead,qcount,wbits=16,wch=2;static uint32_t wrate=44100;static double wpos;static int wopen;
#define WHDR_DONE 1
#define WHDR_INQUEUE 0x10
static inline float sample(const Voice *v,uint32_t frame,int ch){
 uint32_t step=(v->bits/8)*v->channels;const uint8_t *p=(v->host?v->host:mem+v->data)+(size_t)frame*step+(v->channels>1?ch:0)*(v->bits/8);
 return v->bits==16?*(const int16_t*)p/32768.f:(*p-128)/128.f;
}
static void mix_voice(Voice *v,float *out,int n){
 uint32_t frames=v->bytes/((v->bits/8)*v->channels);if(!frames){v->playing=0;return;}
 double step=(double)v->rate/RATE;float l=v->gain*(v->pan>0?1-v->pan:1),r=v->gain*(v->pan<0?1+v->pan:1);
 for(int i=0;i<n;i++){
  if(v->pos>=frames){if(v->loop)v->pos=fmod(v->pos,frames);else{v->playing=0;return;}}
  uint32_t f=(uint32_t)v->pos;out[i*2]+=sample(v,f,0)*l;out[i*2+1]+=sample(v,f,1)*r;v->pos+=step;
 }
}
static void mix_wave(float *out,int n){
 double step=(double)wrate/RATE;int fb=(wbits/8)*wch;
 for(int i=0;i<n&&qcount;i++){
  uint32_t h=waveq[qhead],data=*(uint32_t*)(mem+h),len=*(uint32_t*)(mem+h+4),frames=len/fb;
  if(wpos>=frames){*(uint32_t*)(mem+h+16)=(*(uint32_t*)(mem+h+16)&~WHDR_INQUEUE)|WHDR_DONE;qhead=(qhead+1)%WAVEQ;qcount--;wpos-=frames;i--;continue;}
  Voice v={.bits=wbits,.channels=wch,.data=data};uint32_t f=(uint32_t)wpos;
  out[i*2]+=sample(&v,f,0);out[i*2+1]+=sample(&v,f,1);wpos+=step;
 }
}
static OSStatus render(void *ref,AudioUnitRenderActionFlags *flags,const AudioTimeStamp *ts,UInt32 bus,UInt32 n,AudioBufferList *io){
 float *out=io->mBuffers[0].mData;memset(out,0,n*8);
 pthread_mutex_lock(&lock);
 for(int i=0;i<VOICES;i++)if(voices[i].used&&voices[i].playing)mix_voice(&voices[i],out,n);
 if(wopen)mix_wave(out,n);
 pthread_mutex_unlock(&lock);
 for(UInt32 i=0;i<n*2;i++){float s=out[i]*master;out[i]=s>1?1:s<-1?-1:s;}
 if(dump)fwrite(out,8,n,dump);
 return noErr;
}
int au_open(uint8_t *base){
 mem=base;if(unit)return 0;
 if(getenv("METEOR_AUDIO_DUMP"))dump=fopen(getenv("METEOR_AUDIO_DUMP"),"wb");
 AudioComponentDescription d={kAudioUnitType_Output,kAudioUnitSubType_DefaultOutput,kAudioUnitManufacturer_Apple,0,0};
 AudioComponent c=AudioComponentFindNext(NULL,&d);if(!c||AudioComponentInstanceNew(c,&unit))return -1;
 AudioStreamBasicDescription f={RATE,kAudioFormatLinearPCM,kAudioFormatFlagIsFloat|kAudioFormatFlagIsPacked,8,1,8,2,32,0};
 AudioUnitSetProperty(unit,kAudioUnitProperty_StreamFormat,kAudioUnitScope_Input,0,&f,sizeof f);
 AURenderCallbackStruct cb={render,NULL};AudioUnitSetProperty(unit,kAudioUnitProperty_SetRenderCallback,kAudioUnitScope_Input,0,&cb,sizeof cb);
 if(AudioUnitInitialize(unit))return -2;return AudioOutputUnitStart(unit);
}
int au_voice(uint32_t data,uint32_t bytes,uint32_t rate,int channels,int bits){
 pthread_mutex_lock(&lock);int id=-1;
 for(int i=0;i<VOICES;i++)if(!voices[i].used){voices[i]=(Voice){1,0,0,bits,channels,data,bytes,rate,0,1,0};id=i;break;}
 pthread_mutex_unlock(&lock);return id;
}
void au_free(int id){if(id>=0&&id<VOICES){pthread_mutex_lock(&lock);voices[id].used=0;pthread_mutex_unlock(&lock);}}
void au_play(int id,int loop){if(id<0||id>=VOICES)return;pthread_mutex_lock(&lock);voices[id].playing=1;voices[id].loop=loop;pthread_mutex_unlock(&lock);}
void au_stop(int id){if(id>=0&&id<VOICES)voices[id].playing=0;}
int au_status(int id){return id>=0&&id<VOICES&&voices[id].playing?(1|(voices[id].loop?4:0)):0;}
uint32_t au_get_pos(int id){if(id<0||id>=VOICES)return 0;Voice *v=&voices[id];return (uint32_t)v->pos*(v->bits/8)*v->channels;}
void au_set_pos(int id,uint32_t bytes){if(id>=0&&id<VOICES){Voice *v=&voices[id];v->pos=bytes/((v->bits/8)*v->channels);}}
// DirectSound volume is hundredths of a dB (0 … -10000); pan is -10000 (left) … 10000 (right).
void au_volume(int id,int db100){if(id>=0&&id<VOICES)voices[id].gain=db100<=-10000?0:powf(10,db100/2000.f);}
void au_pan(int id,int pan){if(id>=0&&id<VOICES)voices[id].pan=pan<=-10000?-1:pan>=10000?1:(1-powf(10,-fabsf((float)pan)/2000.f))*(pan<0?-1:1);}
void au_freq(int id,uint32_t hz){if(id>=0&&id<VOICES&&hz)voices[id].rate=hz;}
void au_master(float g){master=g;}
void au_wave_open(uint32_t rate,int channels,int bits){pthread_mutex_lock(&lock);wrate=rate;wch=channels;wbits=bits;qhead=qcount=0;wpos=0;wopen=1;pthread_mutex_unlock(&lock);}
int au_wave_write(uint32_t hdr){
 pthread_mutex_lock(&lock);int ok=qcount<WAVEQ;
 if(ok){waveq[(qhead+qcount)%WAVEQ]=hdr;qcount++;*(uint32_t*)(mem+hdr+16)=(*(uint32_t*)(mem+hdr+16)&~WHDR_DONE)|WHDR_INQUEUE;}
 pthread_mutex_unlock(&lock);return ok;
}
void au_wave_reset(void){
 pthread_mutex_lock(&lock);
 while(qcount){uint32_t h=waveq[qhead];*(uint32_t*)(mem+h+16)=(*(uint32_t*)(mem+h+16)&~WHDR_INQUEUE)|WHDR_DONE;qhead=(qhead+1)%WAVEQ;qcount--;}
 wpos=0;pthread_mutex_unlock(&lock);
}
void au_wave_close(void){au_wave_reset();wopen=0;}
uint32_t au_wave_pos(void){return (uint32_t)wpos*(wbits/8)*wch;}
void au_pan_linear(int id,float pan){if(id>=0&&id<VOICES)voices[id].pan=pan<-1?-1:pan>1?1:pan;}
// Host-decoded stream (DirectShow mp3 music): the whole file becomes 16-bit stereo PCM owned by the voice.
int au_stream_open(const char *path){
 CFURLRef url=CFURLCreateFromFileSystemRepresentation(NULL,(const UInt8*)path,strlen(path),false);ExtAudioFileRef f=NULL;
 OSStatus st=ExtAudioFileOpenURL(url,&f);CFRelease(url);if(st)return -1;
 AudioStreamBasicDescription c={RATE,kAudioFormatLinearPCM,kAudioFormatFlagIsSignedInteger|kAudioFormatFlagIsPacked,4,1,4,2,16,0};
 ExtAudioFileSetProperty(f,kExtAudioFileProperty_ClientDataFormat,sizeof c,&c);
 SInt64 frames=0;UInt32 sz=sizeof frames;ExtAudioFileGetProperty(f,kExtAudioFileProperty_FileLengthFrames,&sz,&frames);
 AudioStreamBasicDescription in;sz=sizeof in;ExtAudioFileGetProperty(f,kExtAudioFileProperty_FileDataFormat,&sz,&in);
 size_t cap=(size_t)(frames*(RATE/(in.mSampleRate>0?in.mSampleRate:RATE))+RATE)*4;uint8_t *pcm=malloc(cap);size_t got=0;
 while(got+4096*4<=cap){AudioBufferList b={1,{{2,4096*4,pcm+got}}};UInt32 n=4096;if(ExtAudioFileRead(f,&n,&b)||!n)break;got+=n*4;}
 ExtAudioFileDispose(f);
 pthread_mutex_lock(&lock);int id=-1;
 for(int i=0;i<VOICES;i++)if(!voices[i].used){voices[i]=(Voice){1,0,0,16,2,0,(uint32_t)got,RATE,0,1,0,pcm};id=i;break;}
 pthread_mutex_unlock(&lock);if(id<0)free(pcm);return id;
}
void au_stream_close(int id){
 if(id<0||id>=VOICES)return;pthread_mutex_lock(&lock);void *p=(void*)voices[id].host;voices[id].used=0;voices[id].host=0;pthread_mutex_unlock(&lock);free(p);
}
uint32_t au_length(int id){return id>=0&&id<VOICES?voices[id].bytes:0;}
