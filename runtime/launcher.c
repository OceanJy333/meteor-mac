// input: the .app bundle layout (Contents/Resources/python + runtime); output: embedded Python running runner.py; pos: Mac app entry.
// Python is loaded from inside the bundle, so the app runs on a Mac with no Python installed.
#include <Python.h>
#include <mach-o/dyld.h>
#include <libgen.h>
#include <stdlib.h>
int main(int argc,char **argv){
 char exe[4096],res[4096],home[4200],runner[4200];uint32_t n=sizeof exe;
 if(_NSGetExecutablePath(exe,&n)||!realpath(exe,res))return 1;
 snprintf(exe,sizeof exe,"%s/../Resources",dirname(res));if(!realpath(exe,res))return 1;
 snprintf(home,sizeof home,"%s/python",res);snprintf(runner,sizeof runner,"%s/runtime/runner.py",res);
 setenv("PYTHONHOME",home,1);setenv("PYTHONNOUSERSITE","1",1);setenv("PYTHONDONTWRITEBYTECODE","1",1);
 char *args[]={argv[0],runner,NULL};
 return Py_BytesMain(2,args);
}
