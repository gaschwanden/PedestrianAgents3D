
import java.util.Vector;

import processing.core.PApplet;
import processing.core.PMatrix3D;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.MyGL;
import utility.MyMath;
import utility.SimplePoly;


public class Pointer {
	PApplet 		p;
	
	int				state;						//> 0 means has hit something
	int				activation_state;			// a more comprehensive state - pressed - pressed&seen etc
	boolean			inited3D;
	float			m_age;
	
	// screen positions
	PVector			m_screen;					// screen pos
	PVector			m_pscreen;					// previous screen pos
	PVector			m_fscreen;					// first screen pos

	// pointer projection into the screen:
	PVector			m_nearPt;					// the near point
	PVector			m_fnearPt;  
	PVector			m_pnearPt; 
	PVector			m_ray;						// the ray from the near point to the far point
	PVector			m_fray; 
	PVector			m_pray; 

	// saving some projected points on a plane:
	PVector			m_pos3D;					// pos
	PVector			m_ppos3D;					// prev
	PVector			m_fpos3D;					// first
	
	static final int POINTER_STATE_IDLE			= 0;
	static final int POINTER_STATE_PRESSED		= 1;
	static final int POINTER_STATE_PRESSED_SEEN = 2;
	static final int POINTER_STATE_RELEASED		= 3;
	
	MyGL myGL;
	MyMath myMath;
	
	Vector <PVector> Lasso;
	int lassoRes = 5;

	public OD selectedOD;					// OD
	public int[] selectedVertexRef;			// vertex ref - building num, vertex num
	public Building selectedBuilding;       // building

	public Module selectedModule;

	public SimplePoly tempPoly; // for drawing a temporary building

	// for editing .....
	//public ETH_Particle 		particle;
	//public Vector<ETH_Particle> pts_created;
	//public Vector<ETH_Spring> 	springs_created;
	
	//boolean eventReceived = false;
	
	Pointer(PApplet _p)
	{
		p					= _p;
		state 				= 0;
		activation_state	= POINTER_STATE_IDLE;
		
		m_screen 	= new PVector();					
		m_pscreen 	= new PVector();						
		m_fscreen 	= new PVector();						
		m_nearPt 	= new PVector();						
		m_fnearPt 	= new PVector();	   
		m_ray 		= new PVector();							
		m_fray 		= new PVector();	 
		m_pos3D 	= new PVector();						
		m_ppos3D 	= new PVector();						
		m_fpos3D 	= new PVector();	
		
		myGL = new MyGL(p);
		myMath = new MyMath(p);
		
		//pts_created 	= new Vector<ETH_Particle>();  // to keep track of what this pointer created
		//springs_created = new Vector<ETH_Spring>  ();
		
	}
	
	void activate()
	{
		//////////////////////////////////////////////////////////
		// this function is called from the event handler
		//////////////////////////////////////////////////////////
		//just say we gonna use this pointer
		activation_state	= POINTER_STATE_PRESSED;
		inited3D			= false;
		m_age				= 0;
		Lasso = null;

	}
	void deactivate()
	{
		//////////////////////////////////////////////////////////
		// this function is called from the event handler
		//////////////////////////////////////////////////////////
		// tell we are not currently using this pointer
		
		//fprintf(stdout, "released at age %f\n", m_age);
		activation_state	= POINTER_STATE_RELEASED;
		//inited3D			= false;
		
		//m_pos3D = m_fpos3D = m_ppos3D = null;
	}
	void init2D  (int mouseX, int mouseY)
	{
		//////////////////////////////////////////////////////////
		// this function is called from the event handler
		//////////////////////////////////////////////////////////
		//just set the screen positions
		m_screen.x  = mouseX; m_screen.y  = mouseY; m_screen.z  = 0;
		m_fscreen.x = mouseX; m_fscreen.y = mouseY; m_fscreen.z = 0;
		m_pscreen.x = mouseX; m_pscreen.y = mouseY; m_pscreen.z = 0;
		
	}

	void update2D(int mouseX, int mouseY)
	{
		//////////////////////////////////////////////////////////
		// this function is called from the event handler
		//////////////////////////////////////////////////////////
		//just update the screen positions
		m_age				= 0;  // set the pointer age back to 0!
		
		m_pscreen.x = m_screen.x; m_pscreen.y = m_screen.y; m_pscreen.z = m_screen.z;
		m_screen.x  = mouseX;     m_screen.y  = 880-mouseY;     m_screen.z  = 0;

	}

	public void init3D(PGraphicsOpenGL g3d, float winX, float winY, float winwidth, float winheight) {
		PVector Far  = myGL.unprojectScreenCoords(g3d,winX,     winY,     1,        winwidth, winheight);
		PVector Near = myGL.unprojectScreenCoords(g3d,winX,     winY,     0,		winwidth, winheight);
		PVector Ray = Far.get();
		Ray.sub(Near);
		
		m_ray     = Ray.get();
		m_fray    = Ray.get();
		m_pray	  = Ray.get();
		m_nearPt  = Near.get();
		m_fnearPt = Near.get();
		m_pnearPt = Near.get();
		m_ppos3D = m_pos3D.get();
		m_pos3D = myGL.projectRayToXYPlane(m_nearPt, m_ray, 0);
		m_fpos3D = m_pos3D.get();
//		m_fpos3D.y = -m_fpos3D.y;
		
		
		inited3D = true;
		
	}

	public void update3D(PGraphicsOpenGL g3d, float winX, float winY, float winwidth, float winheight) {
		if (!inited3D) return;

		PVector Far  = myGL.unprojectScreenCoords(g3d,winX,     winY,     1,        winwidth, winheight);
		PVector Near = myGL.unprojectScreenCoords(g3d,winX,     winY,     0,		winwidth, winheight);
		PVector Ray = Far.get();
		Ray.sub(Near);
		
		if (m_pray==null) return;
		m_pray	  = m_ray.get();
		if (m_pnearPt==null) return;
		m_pnearPt = m_nearPt.get();
		if (m_ray==null) return;
		m_ray     = Ray.get();
		if (m_nearPt==null) return;
		m_nearPt  = Near.get();
		
		if (m_pos3D==null) return;
		m_ppos3D = m_pos3D.get();
		m_pos3D = myGL.projectRayToXYPlane(m_nearPt, m_ray, 0);
		//p.println("update: "+m_pos3D.x+" "+m_ppos3D.x);
		
		/*PVector Far  = myGL.unprojectScreenCoords(g3d,winX,     winY,     1,        winwidth, winheight);
		PVector Near = myGL.unprojectScreenCoords(g3d,winX,     winY,     0,		winwidth, winheight);
		PVector Ray = Far.get();
		Ray.sub(Near);
		
		m_pos3D = myGL.projectRayToXYPlane(m_nearPt, m_ray, 0);
		m_ray	  = Ray.get();
		m_nearPt  = Near.get();
		
		Far  = myGL.unprojectScreenCoords(g3d,m_pscreen.x,     m_pscreen.y,     1,        winwidth, winheight);
		Near = myGL.unprojectScreenCoords(g3d,m_pscreen.x,     m_pscreen.y,     0,		winwidth, winheight);
		Ray = Far.get();
		Ray.sub(Near);
		
		m_ppos3D = myGL.projectRayToXYPlane(m_nearPt, m_ray, 0);
		m_pray	  = Ray.get();
		m_pnearPt = Near.get();*/
		
		//p.println("update: "+winX+" "+m_pscreen.x);
		//p.println("        "+m_pos3D.x+" "+m_ppos3D.x);
	}
	
	public void draw()
	{
		if (tempPoly!=null)
			tempPoly.draw(p);
	}
	
	public void drawLasso() {
		if (activation_state==POINTER_STATE_IDLE) return;
		if (Lasso==null) return;
		p.noFill();
		p.stroke(150);
		p.strokeWeight(2);
		//p.smooth();
		
		p.beginShape();
		for (int i = 0; i < Lasso.size(); i++) {
			p.vertex(Lasso.elementAt(i).x, Lasso.elementAt(i).y);
		}
		p.endShape();
		p.strokeWeight(1);
	}
	
	public void initLasso() {
		Lasso = new Vector<PVector>();
		Lasso.addElement(new PVector(m_screen.x,m_screen.y));
	}
	public void updateLasso() {
		if (Lasso!=null ) {
			if (myMath.dist(m_screen.x,m_screen.y,0,Lasso.elementAt(Lasso.size()-1).x, Lasso.elementAt(Lasso.size()-1).y, 0) > lassoRes)
				Lasso.addElement(new PVector(m_screen.x,m_screen.y));
		}
	}
	
	public void finishLasso() {
		if (Lasso!=null ) {
			Lasso = null;
		}
	}
	
	PVector test( PGraphicsOpenGL g3d,int mouseX, int mouseY, int pmouseX, int pmouseY, int width, int height, float panx, float pany)
	{
		
		PVector Far  = myGL.unprojectScreenCoords(g3d,mouseX,     mouseY,     1,     width,     height);
		PVector Near = myGL.unprojectScreenCoords(g3d,mouseX,     mouseY,     0,		width,     height);
		PVector Ray = Far.get();
		Ray.sub(Near);
		PVector pos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
		
		Far  = myGL.unprojectScreenCoords(g3d,pmouseX,     pmouseY,     1,     width,     height);
		Near = myGL.unprojectScreenCoords(g3d,pmouseX,     pmouseY,     0,		width,     height);
		Ray = Far.get();
		Ray.sub(Near);
		PVector fpos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
	
		
		panx += ( pos3d.x-fpos3d.x  ) ;
		pany += ( pos3d.y-fpos3d.y) ;
		
		return new PVector(panx,pany);
	}

}
