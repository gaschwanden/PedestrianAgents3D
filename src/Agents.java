import java.awt.GraphicsDevice;
import java.awt.GraphicsEnvironment;

import TUIO.TuioCursor;
import TUIO.TuioObject;
import TUIO.TuioProcessing;
import TUIO.TuioTime;
import processing.core.PApplet;
import processing.core.PGraphics;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.MyGL;
import utility.MyMath;


public class Agents extends PApplet {
	
	int screen_size_x = 1920;
	int screen_size_y = 1080;
	
	float scaleaccelerator = 0.001f; //0.00001f;
	public static int 	monitor_size_x;
	public static int 	monitor_size_y;
	int 	number_screens 				= 1;		// tuio special on the 3 screen setup in the value lab
	float 	groundplane_size_x 			= 1440;
	float 	groundplane_size_y 			= 880;   	// this is the resolution of the ground plane 
	
	String path;
	//String settingsfile;
	
	Pointer m_pointers[];
	int 	NUM_POINTERS 				= 10;
	boolean do_mouse_events				= true;
	boolean navigationKeys 				= false;
	boolean m_over_button 				= false;
	
	PGraphicsOpenGL p3;
	MyGL	myGL;
	PVector Far;
	PVector Near;
	MyMath  myMath;
	//public ETH_Thread 				thread;
	
	TuioProcessing 					tuioClient;
	boolean do_tuio_pan = false;
	
	Scene scene;

	
	public static void main(String[] args) {
		PApplet.main(new String[] { "--present", "Agents" });
	}
	
	public void setup()
	{
		//generic:
		path = new java.io.File("").getAbsolutePath() + "/text";
		GraphicsEnvironment environment = GraphicsEnvironment.getLocalGraphicsEnvironment();
		GraphicsDevice devices[] = environment.getScreenDevices();
		monitor_size_x= devices[0].getDisplayMode().getWidth();
		monitor_size_y= devices[0].getDisplayMode().getHeight();
				
		if(monitor_size_x<screen_size_x) screen_size_x=monitor_size_x;
		if(monitor_size_y<screen_size_y) screen_size_y=monitor_size_y;
		
//		screen_size_x=monitor_size_x;
//		screen_size_y=monitor_size_y;
				
		//for debugging as an applet:
//		screen_size_x=1200;
//		screen_size_y=800;
//		path = "/Users/gaschwanden/Documents/workspace/Agents_Google_II/text";
//		size(screen_size_x, monitor_size_y);
//		size(screen_size_x,screen_size_y,P3D);
//		System.out.println("path = "+ path);

		String path =  System.getProperty("user.dir");
		path = path.substring(0, path.length()-4);
//		System.out.println("path = "+ path);

//		System.out.println("java library path = " + System.getProperty("user.dir"));
		size(screen_size_x,screen_size_y,OPENGL);
		tuioClient  = new TuioProcessing(this);
		initApp (true);
	}
	
	
	public void draw()
	{
		background(0);
		
		scene.rotZ+=scene.accelZ;
		scene.rotX+=scene.accelX;
		    
		
		scene.accelZ *= 0.9;
		scene.accelX *= 0.9;
		    
		scene.scaled+=scene.scaleaccel;
		if (scene.scaled < scene.minscale) scene.scaled = scene.minscale;
		scene.scaleaccel*=0.8;
	
		//rotate for 3D
		pushMatrix();
			translate(screen_size_x/2,screen_size_y/2,0);  // ok
			scale(scene.scaled);
			
			rotateX(scene.rotX*0.01f);
			rotateZ(-scene.rotZ*0.01f);
			
			translate(-screen_size_x/2.0f,-screen_size_y/2,0f); //  ok

			translate(screen_size_x/2+scene.panX,screen_size_y/2+scene.panY,0);
			
			scene.agent_visibility();
			scene.move_agents();
			scene.projectToScreen((PGraphicsOpenGL) g, screen_size_x, screen_size_y);
			scene.draw();
			
			drawPointers3D();
			
			// 
			p3 = (PGraphicsOpenGL) g;

			do_tuio_pan = false;
			handlePointerEvents(p3);
			
			// finally.. do the pan. not sure why it does not work porperly the other way
			if (do_mouse_events) {
				MousePan(p3);
			}
			else {
				if (do_tuio_pan) TuioPan(p3);
			}
		popMatrix();
		if (p3!=null) {
//			PGraphics.G.glDisable(p3.G.GL_DEPTH_TEST);
		}
		scene.draw2D();
		
	}
	
	
	////////////////////////////////////////////////////////////////////

	private void drawPointers3D() {
		//first check if we are doing mouse events at all
		int start = 0;
		int end   = 1;
		if (!do_mouse_events) { start = 1; end = NUM_POINTERS; }
				
		//println(navigationKeys);
		//button action //////////////////////////////////////////////////////////////////////////
		if (scene.interaction_mode == Scene.mode_BD_add || scene.interaction_mode == Scene.mode_OB_add) {
			for (int i = start; i < end; i++) {	
				m_pointers[i].draw();
			}
		}
	}

	private void initApp(boolean reload) {
		
		myGL = new MyGL(this);
		myMath = new MyMath(this);
		
		m_pointers = new Pointer[NUM_POINTERS];
		for (int i = 0; i < NUM_POINTERS; i++) {
			m_pointers[i] = new Pointer(this);
		}
		
		if (reload) 
		{
			scene = new Scene(this, path);
			setSceneBounds();
		}
	}
	private void setSceneBounds() {
		////////////////////////////////////////////////////////////////////////////////////
		//adjust settings according to dxf size ///////////////////////////////////////////
		//preliminary grounds plane size
		groundplane_size_x = (scene.drawing_maxx-scene.drawing_minx);
		groundplane_size_y = (scene.drawing_maxy-scene.drawing_miny);    
		
		//println(groundplane_size_x);
		//println(groundplane_size_y);
		
		scene.initialscaled 	= min(abs(screen_size_x/groundplane_size_x), abs(screen_size_y/groundplane_size_y));
		//println(initialscaled);
		scene.scaled 			= scene.initialscaled;
		scene.maxscale 			= scene.initialscaled*20;        //initialscaled*3;  //mimimum and maximum scaleability of the scene
		scene.minscale 			= scene.initialscaled/20;       //initialscaled/3;
		
	}
	
	
	
	////////////////////////////////////////////////////////////////////////////
	// interaction
	
	void handlePointerEvents(PGraphicsOpenGL p3)
	{

		int mx,my;
		int num_pressed_pointers = 0;

		//first check if we are doing mouse events at all
		int start = 0;
		int end   = 1;
		if (!do_mouse_events) { start = 1; end = NUM_POINTERS; }
		
		// check navigation keys
		if (do_mouse_events) {
			if (keyPressed && (keyCode== CONTROL || keyCode==157 || keyCode==SHIFT || key==' '))
				navigationKeys = true;
			else navigationKeys = false;
		}
		//println(navigationKeys);
		
		
		//button action //////////////////////////////////////////////////////////////////////////
		for (int i = start; i < end; i++) {	
			mx = (int) m_pointers[i].m_screen.x;
			my = (int) m_pointers[i].m_screen.y;
			if      (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED)  {
	
					m_pointers[i].m_age ++;
					
					
					if (!m_over_button) {  //only want one button pressed at a time///
						if (scene.stats!=null)
							m_over_button = (scene.stats.over( mx, my ) != -1);

					}
					num_pressed_pointers++;
			}
			else if (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED_SEEN) {
			
					if (m_over_button) {
						//network.stats.dragSlider(mx, my);
					}
				
					m_pointers[i].m_age ++;
					num_pressed_pointers++;
					
			}
			else if (m_pointers[i].activation_state == Pointer.POINTER_STATE_RELEASED) {
				scene.fpanPos=null;
				num_pressed_pointers++;
			}
		}
		// release buttons and button action
		if (num_pressed_pointers == 0) {
				if (m_over_button) {
					scene.stats.buttonAction( );
				}		
				m_over_button = false;
				if (scene.stats!=null) scene.stats.releaseButtons(  );
		}
		////////////////////////////////////////////////////////////////////
		// scene interaction tuio special:
		if (!do_mouse_events) {
		//if (!m_over_button && !do_mouse_events) {
			if (num_pressed_pointers==2) {
				// rotate scene if there are more than 3 pointers present	
				onTuioZoom();	
				navigationKeys = true;
			}
			else if (num_pressed_pointers>2) {
				onTuioRotate();
				navigationKeys = true;
			}
		}
		// scene interaction tuio special
		////////////////////////////////////////////////////////////////////
			
		for (int i = start; i < end; i++) {
			mx = (int) m_pointers[i].m_screen.x;
			my = (int) m_pointers[i].m_screen.y;
			
	

			// if navigation keys - reset the age of all pointers
			if (navigationKeys) {
				m_pointers[i].m_age = 0;
			}

			if (!m_over_button) {
				// mouse down
				if (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED) { // if we see the pointer for the first time
					//always init - update 3D pointer - but interact only if not navigating
					m_pointers[i].init3D(p3,mx,my,screen_size_x, screen_size_y);     				// // // // // // // //
					
							scene.onPointerDownRuntime(m_pointers[i],navigationKeys,num_pressed_pointers);
				}
				// mouse dragged
				else if (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED_SEEN) {						
							m_pointers[i].update3D(p3,mx,my,screen_size_x, screen_size_y);			// // // // // // // //
							
							scene.onPointerDragged(m_pointers[i],navigationKeys,num_pressed_pointers);
							
							
				}
				// mouse up...
				else if (m_pointers[i].activation_state == Pointer.POINTER_STATE_RELEASED) {
							
							scene.onPointerUp(m_pointers[i], navigationKeys,num_pressed_pointers);
							m_pointers[i].inited3D = false;

				}
			} 
		}

		//now set the seen state of the pointers
		for (int i = start; i < end; i++) {
			if      (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED) 
					 m_pointers[i].activation_state =  Pointer.POINTER_STATE_PRESSED_SEEN;
			else if (m_pointers[i].activation_state == Pointer.POINTER_STATE_RELEASED) {
					 m_pointers[i].activation_state =  Pointer.POINTER_STATE_IDLE;
			}
		}
		
		if (num_pressed_pointers == 0) { // and release navigation keys
			navigationKeys = false;
		}
	}
	
	public void keyReleased()
	{
		//println(keyCode);
		
		if (key=='r') 
			scene.resetView();
		else if (key=='m') {  // toggle mouse tuio
			do_mouse_events = !do_mouse_events;
		}
		else if (key=='n') {  //
			initApp (false);
		}
		
		
		else if (key=='1') {
			number_screens = 1;
		}
		else if (key=='2') {
			number_screens = 2;
		}
		else if (key=='3') {
			number_screens = 3;
		}
	}
	
	void MousePan( PGraphicsOpenGL g3d)
	{
		if (!mousePressed) return;
		if (!keyPressed)   return;
		if (key != ' ')    return;
		PVector Far  = myGL.unprojectScreenCoords(g3d,mouseX,     mouseY,     1,    width,     height);
		PVector Near = myGL.unprojectScreenCoords(g3d,mouseX,     mouseY,     0,	width,     height);
		PVector Ray = Far.get();
		Ray.sub(Near);
		PVector pos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
		
		Far  = myGL.unprojectScreenCoords(g3d,pmouseX,     pmouseY,     1,  width,     height);
		Near = myGL.unprojectScreenCoords(g3d,pmouseX,     pmouseY,     0,	width,     height);
		Ray = Far.get();
		Ray.sub(Near);
		PVector ppos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
	
		//println("working "+pmouseX+" "+m_pointers[0].m_pscreen.x);
		
		scene.panX += ( pos3d.x-ppos3d.x) ;
		scene.panY += ( pos3d.y-ppos3d.y) ;
	}
	void TuioPan(PGraphicsOpenGL g3d) {
		int mx,my,pmx,pmy;
		
		//for (int i = 0; i < tuioClient.getTuioCursors().size(); i++) {
		for (int i = 1; i < m_pointers.length; i++) {
			if (m_pointers[i].inited3D == false) continue;
			
			mx=(int) m_pointers[i].m_screen.x; my=(int) m_pointers[i].m_screen.y;
			
			pmx=(int) m_pointers[i].m_pscreen.x; pmy=(int) m_pointers[i].m_pscreen.y;
			
			PVector Far  = myGL.unprojectScreenCoords(g3d,mx,     my,     1,    width,     height);
			PVector Near = myGL.unprojectScreenCoords(g3d,mx,     my,     0,	width,     height);
			PVector Ray = Far.get();
			Ray.sub(Near);
			PVector pos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
			
			Far  = myGL.unprojectScreenCoords(g3d,pmx,     pmy,     1,  width,     height);
			Near = myGL.unprojectScreenCoords(g3d,pmx,     pmy,     0,	width,     height);
			Ray = Far.get();
			Ray.sub(Near);
			PVector ppos3d = myGL.projectRayToXYPlane(Near, Ray, 0);
		
			//println("tuio pan "+pmx+" "+mx);
			
			scene.panX += ( pos3d.x-ppos3d.x) ;
			scene.panY += ( pos3d.y-ppos3d.y) ;
			
			return;
		}
	}
	
	
	
	public void mousePressed()
	{
		//println("p");
		if (!do_mouse_events) return;
		
		// to do: navifation keys here
		
		m_pointers[0].activate();  //just say we gonna use this pointer
		m_pointers[0].init2D(mouseX,mouseY);
	}
	public void mouseReleased()
	{
		//println("r");
		if (!do_mouse_events) return;
		
		// to do: navifation keys here
		
		m_pointers[0].deactivate();
	}
	public void mouseDragged()
	{
		if (!do_mouse_events) return;
		
		//update 2D info
		m_pointers[0].update2D(mouseX,mouseY);

		if (keyPressed && (keyCode==CONTROL || keyCode==157)) { // zoom
			scene.scaleaccel +=(pmouseY-mouseY) * scaleaccelerator;
			return;
		}
		if (keyPressed && keyCode==SHIFT) {  // rotate
			scene.accelX+=(pmouseY-mouseY) * 0.1;
			scene.accelZ-=(pmouseX-mouseX) * 0.1;
			return;
		}

	}
	private void onTuioRotate()
	{
		float ax = 0; float ay = 0;
		int num_pressed_pointers = 0;
		for (int i = 1; i < NUM_POINTERS; i++) {
			if      (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED ||
				     m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED_SEEN) {
						ax+=m_pointers[i].m_pscreen.x-m_pointers[i].m_screen.x;
						ay+=m_pointers[i].m_pscreen.y-m_pointers[i].m_screen.y;
						num_pressed_pointers++;
			}
		}
		if (num_pressed_pointers==0) return; // security
		ax/=num_pressed_pointers;
		ay/=num_pressed_pointers;
		scene.accelX+=(ay) * 0.1;
		scene.accelZ-=(ax) * 0.1;
	}
	
	private void onTuioZoom()
	{
		Pointer P1=null, P2=null;
		boolean v1 = false; boolean v2 = false;

		// find the 2 pointers
		int c = 0;
		for (int i = 1; i < NUM_POINTERS; i++) {
			if      (m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED ||
				     m_pointers[i].activation_state == Pointer.POINTER_STATE_PRESSED_SEEN) {
						 if      (c==0) { P1 = m_pointers[i]; c++; }
						 else if (c==1) { P2 = m_pointers[i]; c++; break; }
			}
		}
		if (c < 2) return; // security
		
		if (!P1.inited3D) return;
		if (!P2.inited3D) return;
		
		float dx1 = P1.m_fscreen.x-P1.m_screen.x;
		float dy1 = P1.m_fscreen.y-P1.m_screen.y;
		float dx2 = P2.m_fscreen.x-P2.m_screen.x;
		float dy2 = P2.m_fscreen.y-P2.m_screen.y;
		
		PVector dir1 = new PVector(dx1,dy1);
		PVector dir2 = new PVector(dx2,dy2);
		
		if (dir1.mag()==0 || dir2.mag() ==0) return;
		
		float angle = (PVector.angleBetween(dir1,dir2));
		//println(PVector.angleBetween(dir1,dir2));
		
		if (angle > 1.0f) {
			//zoom
			float ax = P1.m_screen.x-P2.m_screen.x;
			float ay = P1.m_screen.y-P2.m_screen.y; 
			float d1 = sqrt(ax*ax+ay*ay);
			float bx = P1.m_pscreen.x-P2.m_pscreen.x;
			float by = P1.m_pscreen.y-P2.m_pscreen.y; 
			float d2 = sqrt(bx*bx+by*by);
			//println(d1-d2);
			scene.scaleaccel  += (d1-d2) * 0.006;
		}
		else {
			//pan
			//pan(P1);
			do_tuio_pan = true;
		}
	}
	
	// called when an object is added to the scene
	public void addTuioObject(TuioObject tobj) {
	  //println("add object "+tobj.getSymbolID()+" ("+tobj.getSessionID()+") "+tobj.getX()+" "+tobj.getY()+" "+tobj.getAngle());
		//println(tuioClient.getTuioObjects().size());
	}

	// called when an object is removed from the scene
	public void removeTuioObject(TuioObject tobj) {
	  //println("remove object "+tobj.getSymbolID()+" ("+tobj.getSessionID()+")");
	}

	// called when an object is moved
	public void updateTuioObject (TuioObject tobj) {
	  //println("update object "+tobj.getSymbolID()+" ("+tobj.getSessionID()+") "+tobj.getX()+" "+tobj.getY()+" "+tobj.getAngle()
	          //+" "+tobj.getMotionSpeed()+" "+tobj.getRotationSpeed()+" "+tobj.getMotionAccel()+" "+tobj.getRotationAccel());
	}
	
	public void addTuioCursor(TuioCursor tcur) {
		println("add");
		//println(tuioClient.getTuioCursors().size());
	
		int ID = tcur.getCursorID() + 1;
		if (ID >= m_pointers.length) return; 
		
		m_pointers[ID].activate();  //just say we gonna use this pointer
		int x = tcur.getScreenX(screen_size_x) * number_screens;
		int y = tcur.getScreenY(screen_size_y);
		//int x = tcur.getScreenX(getWidth ());//  - (*m_screen_pos_x);
		//int y = tcur.getScreenY(getHeight());// - (*m_screen_pos_y);
		m_pointers[ID].init2D(x,y);
		
		scene.panX0 = scene.panX;
		scene.panY0 = scene.panY;
	}
	
	public void removeTuioCursor(TuioCursor tcur) {
		//println("remove");
		int ID = tcur.getCursorID() + 1;
		if (ID >= m_pointers.length) return; 
		
		m_pointers[ID].deactivate();
	}
	
	public void updateTuioCursor(TuioCursor tcur) {
		//println("   update "+tcur.getCursorID());
		int ID = tcur.getCursorID() + 1;
		if (ID >= m_pointers.length) return; 
		
		//update 2D info
		int x = tcur.getScreenX(screen_size_x) * number_screens;
		int y = tcur.getScreenY(screen_size_y);
		//int x = tcur.getScreenX(monitor_size_x);// - (*m_screen_pos_x);
		//int y = tcur.getScreenY(monitor_size_x);// - (*m_screen_pos_y);
		m_pointers[ID].update2D(x,y);
		
	}
	
	public void refresh(TuioTime bundleTime) {
		//println("fgrgh");
	}

}
