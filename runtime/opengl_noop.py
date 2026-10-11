# input: guest opengl32 call without a current context; output: Windows no-context result; pos: GL import shim.
# stdcall argument counts for the opengl32/glu32 imports Meteor.exe uses.
ARGS={'glNormalPointer':3,'glGenLists':1,'glBlendFunc':2,'glDepthFunc':1,'glAlphaFunc':2,'glTexParameterf':3,'glPolygonMode':2,'glDepthMask':1,
 'glColor4ubv':1,'glEnable':1,'glTexParameteri':3,'glGetTexParameteriv':3,'glGenTextures':2,'glDeleteTextures':2,'glBindTexture':2,'glGetFloatv':2,
 'glLoadMatrixf':1,'glGetIntegerv':2,'glMatrixMode':1,'glDisable':1,'glShadeModel':1,'glEnableClientState':1,'glDisableClientState':1,'glDrawElements':4,
 'glTexCoordPointer':4,'glDrawArrays':3,'glColorPointer':4,'glVertexPointer':4,'gluBuild2DMipmaps':7,'wglGetProcAddress':1,'wglUseFontBitmapsA':4,'SwapBuffers':1,'glGetError':0}
def noop(n,a):
 if n not in ARGS:raise NotImplementedError('no-context '+n)
 return 0,ARGS[n]
