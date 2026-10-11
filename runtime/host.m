// input: game resolution, GL frames and macOS events; output: Retina window, game-space mouse/keyboard state; pos: native presentation bridge.
#import <AppKit/AppKit.h>
#import <OpenGL/gl.h>
static NSOpenGLContext *glcontext;
@interface MeteorView:NSView @end
@implementation MeteorView
-(void)drawRect:(NSRect)rect {}
-(BOOL)acceptsFirstResponder{return YES;}
-(void)keyDown:(NSEvent*)e{} // swallow so AppKit does not beep; keys are tracked in host_pump
@end
// Closing the window quits, like the original's single window.
@interface MeteorDelegate:NSObject<NSWindowDelegate> @end
@implementation MeteorDelegate
-(void)windowWillClose:(NSNotification*)n{[NSApp terminate:nil];}
@end
static MeteorDelegate *delegate;
static NSWindow *window;static MeteorView *view;static unsigned char keys[256];
static int W=640,H=480,mouseX,mouseY,rawX,rawY,captured;static unsigned buttons;static NSMutableArray *events;
static NSString *title=@"流星蝴蝶剑";
// Game-space rectangle inside the view (points), letterboxed to keep W:H.
static NSRect game_rect(void){
 NSSize b=view.bounds.size;double s=fmin(b.width/W,b.height/H);double w=W*s,h=H*s;return NSMakeRect((b.width-w)/2,(b.height-h)/2,w,h);
}
static void capture(int on){
 if(on==captured)return;captured=on;CGAssociateMouseAndMouseCursorPosition(!on);
 if(on)[NSCursor hide];else [NSCursor unhide];
 window.title=on?[title stringByAppendingString:@"  —  按 ⌘ 释放鼠标"]:[title stringByAppendingString:@"  —  点击画面锁定鼠标"];
}
void host_set_mode(int width,int height){W=width;H=height;if(window)window.contentAspectRatio=NSMakeSize(W,H);}
// Standard app/window menus give ⌘Q, ⌘M and ⌃⌘F their usual meaning.
static void menus(void){
 NSMenu *bar=[NSMenu new],*app=[NSMenu new],*win=[[NSMenu alloc] initWithTitle:@"窗口"];
 NSMenuItem *a=[NSMenuItem new],*w=[NSMenuItem new];a.submenu=app;w.submenu=win;[bar addItem:a];[bar addItem:w];
 [app addItemWithTitle:@"隐藏流星蝴蝶剑" action:@selector(hide:) keyEquivalent:@"h"];[app addItem:NSMenuItem.separatorItem];
 [app addItemWithTitle:@"退出流星蝴蝶剑" action:@selector(terminate:) keyEquivalent:@"q"];
 [win addItemWithTitle:@"最小化" action:@selector(performMiniaturize:) keyEquivalent:@"m"];
 NSMenuItem *fs=[win addItemWithTitle:@"进入全屏" action:@selector(toggleFullScreen:) keyEquivalent:@"f"];fs.keyEquivalentModifierMask=NSEventModifierFlagCommand|NSEventModifierFlagControl;
 NSApp.mainMenu=bar;NSApp.windowsMenu=win;
}
void host_open(int width,int height){
 W=width;H=height;[NSApplication sharedApplication];[NSApp setActivationPolicy:NSApplicationActivationPolicyRegular];menus();[NSApp finishLaunching];
 NSRect screen=NSScreen.mainScreen.visibleFrame;double s=fmax(fmin(screen.size.width*0.85/W,screen.size.height*0.85/H),1.0);
 window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,W*s,H*s) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable|NSWindowStyleMaskMiniaturizable|NSWindowStyleMaskResizable backing:NSBackingStoreBuffered defer:NO];
 window.contentAspectRatio=NSMakeSize(W,H);window.collectionBehavior=NSWindowCollectionBehaviorFullScreenPrimary;
 view=[[MeteorView alloc] initWithFrame:NSMakeRect(0,0,W*s,H*s)];view.wantsBestResolutionOpenGLSurface=YES;
 delegate=[MeteorDelegate new];window.delegate=delegate;window.contentView=view;window.acceptsMouseMovedEvents=YES;[window makeFirstResponder:view];[window center];[window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
 events=[NSMutableArray new];captured=-1;capture(0);
}
static int vk(NSEvent *e){
 switch(e.keyCode){case 53:return 27;case 49:return 32;case 36:return 13;case 48:return 9;case 51:return 8;case 123:return 37;case 124:return 39;case 125:return 40;case 126:return 38;
  case 122:return 112;case 120:return 113;case 99:return 114;case 118:return 115;case 96:return 116;case 97:return 117;case 98:return 118;case 100:return 119;case 101:return 120;case 109:return 121;}
 NSString *s=e.charactersIgnoringModifiers.uppercaseString;return s.length?[s characterAtIndex:0]&255:0;
}
static void move_to(int x,int y,unsigned msg){
 mouseX=x<0?0:x>=W?W-1:x;mouseY=y<0?0:y>=H?H-1:y;
 [events addObject:@[@(msg),@((buttons&1)|((buttons&2)?2:0)),@((mouseX&0xffff)|((mouseY&0xffff)<<16))]];
}
void host_pump(void){
 @autoreleasepool{
 NSEvent *e;
 while((e=[NSApp nextEventMatchingMask:NSEventMaskAny untilDate:[NSDate distantPast] inMode:NSDefaultRunLoopMode dequeue:YES])){
  NSEventType t=e.type;
  if(t==NSEventTypeKeyDown||t==NSEventTypeKeyUp){
   if(e.modifierFlags&NSEventModifierFlagCommand){[NSApp sendEvent:e];continue;} // ⌘ shortcuts stay with macOS
   int k=vk(e);if(t==NSEventTypeKeyDown&&e.ARepeat)continue;
   keys[k]=t==NSEventTypeKeyDown?128:0;[events addObject:@[@(t==NSEventTypeKeyDown?256:257),@(k),@(0)]];
   // J / K stand in for the left / right button, so a trackpad hand never has to click while swiping.
   if(k=='J'||k=='K'){unsigned b=k=='J'?1:2,down=t==NSEventTypeKeyDown;if(down)buttons|=b;else buttons&=~b;move_to(mouseX,mouseY,b==1?(down?0x201:0x202):(down?0x204:0x205));}
   continue;
  }
  // Two-finger swipe = camera look (trackpad / Magic Mouse). Wheel-style mice have no precise deltas and are left alone.
  if(t==NSEventTypeScrollWheel&&(e.window==window||!e.window)&&e.hasPreciseScrollingDeltas){
   static double fx,fy;double k=2.0*W/game_rect().size.width,sign=e.directionInvertedFromDevice?1:-1;
   fx+=sign*e.scrollingDeltaX*k;fy+=sign*e.scrollingDeltaY*k;int ix=(int)fx,iy=(int)fy;rawX+=ix;rawY+=iy;fx-=ix;fy-=iy;continue;
  }
  if(t==NSEventTypeFlagsChanged){
   NSEventModifierFlags f=e.modifierFlags;keys[17]=(f&NSEventModifierFlagControl)?128:0;keys[16]=(f&NSEventModifierFlagShift)?128:0;keys[18]=(f&NSEventModifierFlagOption)?128:0;
   if(f&NSEventModifierFlagCommand)capture(0);
  }
  int mouse=t==NSEventTypeMouseMoved||t==NSEventTypeLeftMouseDragged||t==NSEventTypeRightMouseDragged||t==NSEventTypeLeftMouseDown||t==NSEventTypeLeftMouseUp||t==NSEventTypeRightMouseDown||t==NSEventTypeRightMouseUp;
  // Uncaptured clicks outside the game view (title bar, traffic lights, resize edge) belong to AppKit.
  if(mouse&&e.window==window&&!captured&&!NSPointInRect([view convertPoint:e.locationInWindow fromView:nil],view.bounds))mouse=0;
  if(mouse&&e.window==window){
   if(!captured&&t==NSEventTypeLeftMouseDown)capture(1);
   if(t==NSEventTypeLeftMouseDown)buttons|=1;if(t==NSEventTypeLeftMouseUp)buttons&=~1;
   if(t==NSEventTypeRightMouseDown)buttons|=2;if(t==NSEventTypeRightMouseUp)buttons&=~2;
   unsigned msg=t==NSEventTypeLeftMouseDown?0x201:t==NSEventTypeLeftMouseUp?0x202:t==NSEventTypeRightMouseDown?0x204:t==NSEventTypeRightMouseUp?0x205:0x200;
   NSRect g=game_rect();double s=W/g.size.width;
   if(captured){rawX+=lround(e.deltaX*s);rawY+=lround(e.deltaY*s);move_to(mouseX+lround(e.deltaX*s),mouseY+lround(e.deltaY*s),msg);}
   else{NSPoint q=[view convertPoint:e.locationInWindow fromView:nil];move_to((q.x-g.origin.x)*s,(g.origin.y+g.size.height-q.y)*s,msg);}
   if(captured&&msg!=0x200){} // clicks while captured already queued by move_to
  }
  if(!mouse||e.window!=window)[NSApp sendEvent:e];
 }
 if(captured&&!window.isKeyWindow)capture(0);
 [NSApp updateWindows];
 }
}
int host_key(int key){return keys[key&255]?0x8000:0;}
// 0/1: game-space cursor, 2: buttons, 3/4: unclamped raw motion for DirectInput look.
int host_mouse(int axis){return axis==0?mouseX:axis==1?mouseY:axis==2?buttons:axis==3?rawX:rawY;}
int host_message(unsigned *msg,int remove){if(!events.count)return 0;NSArray *e=events.firstObject;for(int i=0;i<3;i++)msg[i]=[e[i] unsignedIntValue];if(remove)[events removeObjectAtIndex:0];return 1;}
void host_gl_open(void){
 NSOpenGLPixelFormatAttribute attrs[]={NSOpenGLPFADoubleBuffer,NSOpenGLPFAColorSize,24,NSOpenGLPFAAlphaSize,8,NSOpenGLPFADepthSize,24,
  NSOpenGLPFAMultisample,NSOpenGLPFASampleBuffers,1,NSOpenGLPFASamples,4,NSOpenGLPFAAccelerated,0};
 NSOpenGLPixelFormat *format=[[NSOpenGLPixelFormat alloc] initWithAttributes:attrs];
 glcontext=[[NSOpenGLContext alloc] initWithFormat:format shareContext:nil];GLint one=1;[glcontext setValues:&one forParameter:NSOpenGLContextParameterSwapInterval];
 [glcontext setView:view];[glcontext makeCurrentContext];glEnable(GL_MULTISAMPLE);
}
// Drawable size in pixels and the letterboxed game rectangle in pixels (x,y from bottom-left).
void host_gl_drawable(int *out){
 NSRect b=[view convertRectToBacking:view.bounds],g=[view convertRectToBacking:game_rect()];static NSSize last;
 if(!NSEqualSizes(last,b.size)){last=b.size;[glcontext update];}
 out[0]=b.size.width;out[1]=b.size.height;out[2]=g.origin.x;out[3]=g.origin.y;out[4]=g.size.width;out[5]=g.size.height;
}
void host_gl_swap(void){[glcontext flushBuffer];}
void host_present(const unsigned char *pixels,int width,int height,int bits){}
