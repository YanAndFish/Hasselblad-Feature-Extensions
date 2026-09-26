from pathlib import Path
import sys,json,importlib.util,hashlib
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parents[1];ROOT=P.parents[3]
sys.path.insert(0,str(ROOT/'x1d/wireless-flash/build/ui-test-python'))
from PySide6.QtCore import QCoreApplication
from PySide6.QtQml import QJSEngine
app=QCoreApplication([]);j=QJSEngine()
s=(P/'qml/liveview/Touchpad.qml').read_text();f=s[s.index('    function updateAfIndexRelativePosition'):s.index('    function updateZoomPosition')]
setup="var padWidth=300,padHeight=225,width=1000,height=750,xLastPos=100,yLastPos=100,continuousFocusX=.5,continuousFocusY=.5;var afc={gridXMargin:150,gridYMargin:125,afItemWidth:100,afItemHeight:100,xCount:7,yCount:5};var GlobalStateInfo={afSselectedIndex:17,focusDelivery:{select:function(p){Camera.focus_point=p}}};var Camera={focus_point:null,combine:function(x,y){return [x,y]}};"
r=j.evaluate(setup+f);assert not r.isError(),r.toString()
def run(code):
 r=j.evaluate(code);assert not r.isError(),r.toString();return r.toVariant()
run('updateAfIndexRelativePosition(101,101)');point=run('Camera.focus_point');assert abs(point[0]-(.5+1/300))<1e-8 and abs(point[1]-(.5+1/225))<1e-8
run('updateAfIndexRelativePosition(102,102)');point=run('Camera.focus_point');assert abs(point[0]-(.5+2/300))<1e-8
run('updateAfIndexRelativePosition(10000,10000)');assert run('Camera.focus_point')[0]==.8
run('updateAfIndexRelativePosition(9999,9999)');assert run('Camera.focus_point')[0]<.8
assert 'beginFocusDrag()' in s and s.count('beginFocusDrag()')==3
spec=importlib.util.spec_from_file_location('native_roi',ROOT/'x1d/af-experiment/CodeTests/inspect_roi_native.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
cases=[]
for size in [(450,600),(630,840),(900,1200)]:
 prev=None
 for x in [4370,4430,5000,5020,5050,5190]:
  roi=m.original_roi(size,(x,4280));assert prev is None or roi['left']>prev;prev=roi['left'];cases.append(dict(size=size,x=x,roi=roi))
(P/'build/viewfinder-touch/continuous-roi-validation.json').write_text(json.dumps(dict(passed=True,evfCases=4,nativeROICases=cases,hardwareRequests=0,sourceSha256=hashlib.sha256(s.encode()).hexdigest()),indent=2))
print('EVF small movements, boundary reversal and 18 native ROI cases passed')
