import processing.core.PApplet;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.MyGL;


public class OD {
	PApplet p;
	public PVector pos;
	public PVector posS;
	public float weight 	= 1;
	public float oWeight 	= 1;
	public float dWeight 	= 1;
	float d 				= 5;
	
	int group = 0;
	
	boolean processed = false;
	
	MyGL myGL;
	
	
	OD(PApplet _p, float x, float y, float z, int g)
	{
		p=_p;
		pos = new PVector(x,y,z);
		posS = new PVector();
		myGL = new MyGL(p);
		
		group = g;
	}
	
	public void draw(Scene scene)
	{
		if (scene.analysis_mode == Scene.display_facadevisibility ||
			scene.analysis_mode == Scene.display_noAnalysis ||
					scene.analysis_mode == Scene.display_pathoverlap) {
			if (scene.interaction_mode == Scene.mode_OD ||
					scene.interaction_mode == Scene.mode_OD_delete ||
					scene.interaction_mode == Scene.mode_OD_weight ){
			// nothing
			}
			else {
				return; // dont draw
			}
		}
		p.noStroke();
		p.fill(255);
		if (scene.analysis_mode == Scene.display_facadevisibilityO) {
			/*if (scene.ods[0] !=null) {
				if (scene.ods[0]==this) p.fill(255,0,0);
			}
			if (scene.ods[1] !=null) {
				if (scene.ods[1]==this) p.fill(0,255,0);
			}
			if (scene.ods[2] !=null) {
				if (scene.ods[2]==this) p.fill(0,0,255);
			}*/
			if (group==0) {
				p.fill(255,0,0);
			}
			else if (group==1) {
				p.fill(0,255,0);
			}
			else if (group==2) {
				p.fill(0,0,255);
			}
			
		}
		p.pushMatrix();
			p.translate(pos.x,pos.y,pos.z);
			p.ellipseMode(p.CENTER);
			p.ellipse(0,0, d*oWeight,d*oWeight);
		p.popMatrix();
	}
	
	public void drawScreen(Scene scene)
	{
		if (posS==null) return;
		
		if (scene.interaction_mode == Scene.mode_OD_weight) {
			p.fill(100);
			p.textAlign(PApplet.CENTER);
			p.text("O: "+(int)(oWeight*100), posS.x,posS.y-7);
			p.text("D: "+(int)(dWeight*100), posS.x,posS.y+13);
		}
		
	}

	public void project(PGraphicsOpenGL g3d, int winW, int winH) {

	      float [] coords = new float[4];
	      int res = myGL.projectScreenCoords(g3d, pos.x, pos.y, pos.z, coords, winW, winH);
	      posS.x = (int)coords[0];
	      posS.y = (int)coords[1]; 
	      posS.z = (int)coords[2]; //note! if coords[2] >= 1 the result is not valid
		
	}

	public void weightO(float f) {
		float incr = 0.02f;
		if (f<-1)    oWeight+=incr;
		else if(f>1) oWeight-=incr;
		if (oWeight > 1) oWeight = 1;		
		if (oWeight <0) oWeight = 0;
	}
	public void weightD(float f) {
		float incr = 0.02f;
		if (f<-1) dWeight+=incr;
		else if(f>1) dWeight-=incr;
		if (dWeight > 1) dWeight = 1;		
		if (dWeight <0) dWeight = 0;
		
	}
	
}
