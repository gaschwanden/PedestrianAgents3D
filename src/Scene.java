import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.DXFFace;
import utility.DXFHandler;
import utility.DXFLWPoly;
import utility.DXFLine;
import utility.DXFMesh;
import utility.DXFPoly;
import utility.DXFVertex;
import utility.MyGL;
import utility.MyMath;
import utility.SimplePoly;


public class Scene {
	PApplet p;
	Vector <Building> buildings;
	Vector <Building> obstacles;
	Vector <Landmark> landmarks;
	Vector<Module> modules;
	Vector<Module> placedModules;
	Site site;
	OD[] ods;
	Vector<Agent> agents;
	
	Grid grid;
	float gridsize = 4; // 7
	
	public String folderpath;
	String buildingspath;
	String sitepath;
	String modulepath;
	String obstaclespath;
	String ODpath;
	String[] landmarkpath;
	Vector<rect> partialGridUpdater;
	Vector<Trace>traces;
	
	Isovist iso;
	
	//rotation and scale...................
		float 	rotZ						= 0;
		float 	rotX						= 0;
		float 	accelZ						= 0;
		float 	accelX						= 0;
		float 	rotationacceleration_tuio  	= 0.02f;    // how much acceleration per pointer movement
		float 	rotationacceleration_mouse 	= 0.01f; 

		float 	scaled                    	= 1;        // the current scale
		float 	initialscaled             	= 0.01f;    // the initial scale
		float 	scaleaccel                	= 0;        // the current scale transformation
		float 	maxscale                  	= 2.0f;       
		float 	minscale                  	= 0.001f;    
		float 	scaleacceleration_tuio    	= 0.0002f;  // how much acceleration per pointer movement  
		float 	scaleacceleration_mouse   	= 0.02f;     

		float   panX 						= 0;
		float   panY 						= 0;
		float   panX0 						= 0;
		float   panY0						= 0;
		PVector panPos=null; PVector fpanPos=null;  	// the panning needs a bit of extra care and tracking,
			                                            // as the ground plane changes as you pan
	//rotation and scale...................

	public static final int mode_noInteraction			= 0;
	
	public static final int mode_OD 					= 1;
	public static final int mode_OD_delete				= 2; 
	public static final int mode_OD_weight				= 3;
	
	public static final int mode_BD_add					= 10; 
	public static final int mode_BD_edit				= 11; 
	public static final int mode_BD_move				= 12;
	public static final int mode_BD_delete				= 13; 
	
	//public static final int mode_Iso				    = 30;
	
	public static final int mode_MD_add					= 40;
	public static final int mode_MD_move				= 41;
	public static final int mode_MD_rotate				= 42;
	public static final int mode_MD_delete				= 43;
	
	public static final int mode_OB_add					= 50; 
	public static final int mode_OB_edit				= 51;
	public static final int mode_OB_move				= 52;
	public static final int mode_OB_delete				= 53; 
	
	public static final int display_noAnalysis			= 0;
	public static final int display_pathoverlap			= 1;
	public static final int display_facadevisibility	= 2;
	public static final int display_facadevisibilityO	= 3;
	
	public static final int display_traces				= 4;
	public static final int display_tracesO				= 5;
	
	public static final int NUM_AGENTS					= 300;
	int release_rate 									= 20; // 0-100 how fast the agents should be released
	
	public static int    	interaction_mode = mode_noInteraction;
	public static int       analysis_mode = display_noAnalysis;
	
	public boolean show_iso = false;
	
	public static final int max_num_OD 					= 50;
	
	public static final float tol 						= 12; // screen hit tol
	
	public static final int TRACERESO 					= 5;
	public static final int TRACERESOSTRAIGHT 			= 5;
	public static final boolean DO_AGEING_TRACES 		= true;
	public static final boolean SMOOTHTRACE 			= true;
	
	
	
	boolean needsAnalysisReset;
	boolean notifyAppRenew = false;
	boolean notifySaveODs = false;
	boolean notifyLoadODs = false;
	boolean notifySaveBuildings = false;
	boolean notifyLoadBuildings = false;
	boolean notifySaveObstacles = false;
	boolean notifyLoadObstacles = false;
	
	
	float drawing_minx = 9999999999.9f;
	float drawing_miny = 9999999999.9f;
	float drawing_maxx = -9999999999.9f;
	float drawing_maxy = -9999999999.9f;
	
	float xoffs;
	float yoffs;
	
	float scaler  = 0.001f;
	
	
	
	Grid_Thread thread;
	Statistics stats;
	
	float radiusDevider   = PApplet.PI/10.0f;
	int coneVision        = 100;
	
	MyMath myMath;
	MyGL myGL;
	public boolean blur_pathoverlap  = true;
	public float blurdecay = 0.5f;
	
	
	public Scene(PApplet _p, String path)
	{
		p=_p;
		folderpath = path.substring(0, path.length()-8);
		buildingspath = folderpath + "/"+"text/"+"GBuildings.dxf";//"buildingsS.dxf";
		obstaclespath = folderpath+ "/"+"text/" +"GObstacles.dxf";//"obstaclesS2.dxf";//"/"+"obstacles.dxf";//"obstacles_minimal.dxf";
		sitepath = folderpath +  "/"+"text/"+"GSite.dxf"; // "siteS.dxf"
		modulepath = folderpath + "/"+"text/"+"module.dxf";
		landmarkpath = new String[1];
		//landmarkpath[0] = path + "/"+"barrage_simple.dxf";
		//landmarkpath[1] = path + "/"+"flowerdomes1.dxf";
		landmarkpath[0] = path + "/"+"text/"+"MBS.dxf";
		ODpath = path +"text/"+"GOD.txt";
		//landmarkpath[3] = path + "/"+"supertrees.dxf";
		myMath = new MyMath(p);
		myGL = new MyGL(p);
		
		init();
		
		thread = new Grid_Thread(this, p);
		stats = new Statistics(p, this);
//		thread.loadODs(ODpath);
	}

	public void init() {
		partialGridUpdater = new Vector<rect> ();
		ods = new OD[max_num_OD];
		agents = new Vector<Agent> ();
		traces = new Vector<Trace>();
		
		//
		importSite();
		importBuildings();
		importObstacles();
		//inportLandmarks();
		
		
		centerScene();
		
		grid = new Grid(p, drawing_minx, drawing_miny, drawing_maxx, drawing_maxy, gridsize, max_num_OD, buildings, obstacles, site.poly);
		if (buildings!=null) {
			for (int i = 0; i < buildings.size(); i++) {
				buildings.elementAt(i).footprint.calculateGriddedSegments(this);
			}
		}
		
		placedModules = new Vector<Module>();
		
		notifyAppRenew = false;
		notifySaveODs = false;
		notifyLoadODs = false;
	}
	
	void resetView() {
		rotZ=0;
		rotX=0;
		panX = 0;
		panY = 0;

		accelZ=0;
		accelX=0;
		scaled = initialscaled;
		scaleaccel = 0;
	}
	
	public void draw() {
		grid.draw(analysis_mode);
	//	site.draw(analysis_mode);
		
		for (int i = 0; i < placedModules.size(); i++) {
			placedModules.elementAt(i).draw();
		}
		if (buildings!=null) {
			for (int i = 0; i < buildings.size(); i++) {
				buildings.elementAt(i).draw(analysis_mode);
			}
		}
		if (obstacles!=null) {
			//p.println(obstacles.size());
			for (int i = 0; i < obstacles.size(); i++) {
				obstacles.elementAt(i).drawAsObstacle(analysis_mode);
			}
		}
		
		if (landmarks!=null) {
			for (int i = 0; i < landmarks.size(); i++) {
				landmarks.elementAt(i).draw(analysis_mode);
			}
		}
		for (int i = 0; i < ods.length; i++) {
			if (ods[i]!=null) ods[i].draw(this);
		}
		for (int i = 0; i < agents.size(); i++) {
			agents.elementAt(i).draw();
		}

		for (int i = 0; i < traces.size(); i++) {
			if (traces.elementAt(i).drawMe) {  // draw every third trace only
				if (analysis_mode == this.display_traces) {
					traces.elementAt(i).draw(false, this);
				}
				else if (analysis_mode == this.display_tracesO) {
					traces.elementAt(i).draw(true, this);
				}
			}
			traces.elementAt(i).update(this);
		}
		
		if (iso!=null) iso.draw();
		
		//release agents
		releaseAgents();
	}
	
	public void draw2D() {
		if (stats!=null) stats.draw();
		if (buildings!=null) {
			for (int i = 0; i < buildings.size(); i++) {
				buildings.elementAt(i).draw2D(analysis_mode);
			}
		}
		if (obstacles!=null) {
			for (int i = 0; i < obstacles.size(); i++) {
				obstacles.elementAt(i).draw2D(analysis_mode);
			}
		}
		for (int i = 0; i < ods.length; i++) {
			if (ods[i]==null) continue;
			ods[i].drawScreen(this);
		}
	}
	
	public void notifyResetAnalysis() {
		needsAnalysisReset = true;
	}
	
	private void releaseAgents()
	{
		// global release agents
		
		if (analysis_mode == Scene.display_pathoverlap
				||  analysis_mode == Scene.display_facadevisibility
				||  analysis_mode == Scene.display_facadevisibilityO
				||  analysis_mode == Scene.display_traces
				||  analysis_mode == Scene.display_tracesO) {
					if (agents.size() < NUM_AGENTS - 1) {
						if (p.random(100) < release_rate) {
							
							//first check num available targets
							int num= 0;
							for (int i = 0; i < ods.length; i++) {
								if (ods[i]!=null) num++;
							}
							if (num<2) return;
							
							// now release
							Agent a = new Agent(p,grid.gridsize, grid.sx, grid.sy, this);
							agents.addElement(a);
						}
					}
				}
	}
	
	//////////////////////////////////////////////////////////////////////////
	// project
	
	public void projectToScreen(PGraphicsOpenGL g3d, int winW, int winH) {
		float[] coords;
		if (interaction_mode == mode_OD ||
			interaction_mode == mode_OD_delete ||
			interaction_mode == mode_OD_weight) {
			for (int i = 0; i < ods.length; i++) 
			{
				if (ods[i]!=null) ods[i].project(g3d, winW, winH);
			}
		}
		else if (interaction_mode == mode_BD_edit || 
				 interaction_mode == mode_BD_move ||
				 interaction_mode == mode_BD_delete ) {
			if (buildings!=null) {
				//p.println(buildings.size());
				for (int i = 0; i < buildings.size(); i++) 
				{
					buildings.elementAt(i).project(g3d, winW, winH);
				}
			}
			
		}
		else if (interaction_mode == mode_OB_edit || 
				 interaction_mode == mode_OB_move ||
				 interaction_mode == mode_OB_delete ) {
			if (obstacles!=null) {
				for (int i = 0; i < obstacles.size(); i++) 
				{
					obstacles.elementAt(i).project(g3d, winW, winH);
				}
			}
			
		}
		else if (interaction_mode == mode_MD_add || 
				 interaction_mode == mode_MD_move ||
				 interaction_mode == mode_MD_rotate ||
				 interaction_mode == mode_MD_delete ) {
			if (placedModules!=null) {
				for (int i = 0; i < placedModules.size(); i++) 
				{
					placedModules.elementAt(i).project(g3d, winW, winH);
				}
			}
		}
	}
	
	//////////////////////////////////////////////////////////////////////////
	// agents
	
	 void move_agents()
	  {
	      PVector vv = new PVector();
	      
	      /*for (int i=0;i<agents.size();i++)
	      {
	    	  Agent a = agents.elementAt(i);
	    	  if (!a.active)          continue;
	    	  a.vx=0.0; a.vy=0.0;
	        
	    	  move_vis_setDwellingTowardsTarget(i);
	      }*/
	      
	      //move_vis_repelPeople();  // //
	      
	      for (int i=0;i<agents.size();i++)
	      {
	    	  Agent a = agents.elementAt(i);
	    	  if (!a.active)          continue;
	        
	    	  a.setDirToTarget();
	        
	    	  a.move();
	          
	    	  a.markOccupancy();
	            
	    	  //check if target reached
	    	  a.TargetCheck();   
	      }    
	  }  
	  
	
	void agent_visibility()
	{
	    p.stroke(255,255,0);
	    //p.println("ho "+agents.size());
	    for (int k=0;k<agents.size();k++)
	    {
	    	Agent a = agents.elementAt(k);
	    	if (a.active == false) continue;
	      
	    	//error handling
	    	if (a.px < 0) continue; if (a.px >= grid.gridPoints.length)    continue;
	    	if (a.py < 0) continue; if (a.py >= grid.gridPoints[0].length) continue;
	      
	    	/// what is the longest line of sight that is towards our target?
	    	float maxsightlength = 0;  //mini
	    	int minpix = -1;
	    	//float currD = cityMap.distance[target[k]][(int)px[k]][(int)py[k]];  
	    	float currD = grid.gridPoints[(int)a.px][(int)a.py].dist[a.target];
	    	a.far_px = -1; a.far_py = -1;
	    	/// 
	    	// to make a weighted draw rather than taking the longest line of sight!
	    	Vector possPixs = new Vector();
	    	Vector weights = new Vector();
	    	//
	    	float angle = 0;  //the initial direction we are looking into
	    	float x = 0; float y = 0;
	    	if(a.vy!=0) angle = -PApplet.atan(a.vx/a.vy);
	    	if(a.vy< 0) angle = PApplet.PI+PApplet.atan(a.vx/-a.vy);  
	      
	      
	    	for(float j=angle ;j <PApplet.PI+angle+radiusDevider ;j+=radiusDevider) {  // // // // //
	    		float x1 = 0;
	    		float y1 = 0;
	    		float x2 = x;
	    		float y2 = y;
	    		int pixx=(int)(a.px);
	    		int pixy=(int)(a.py);
	    		for(int i = 1; i  < coneVision; i += 1) {

	    			x = i * PApplet.cos(j);
	    			y = i * PApplet.sin(j);

	    			pixx = (int)(a.px + x);
	    			pixy = (int)(a.py + y);
	          
	    			if (pixx >= grid.gridPoints.length    || pixx < 0) break; 
	    			if (pixy >= grid.gridPoints[0].length || pixy < 0) break;
	          
	    			//if (a.origin>= 0 && a.origin < grid.gridPoints[pixx][pixy].visibilityO.length)
	    				//grid.gridPoints[pixx][pixy].visibilityO[a.origin] += 1;
	    			try {
	    				if (a.origin >= 0 && a.origin<ods.length) {
	    					if (ods[a.origin].group < grid.gridPoints[pixx][pixy].visibilityO.length)
	    						grid.gridPoints[pixx][pixy].visibilityO[ods[a.origin].group] += 1;
	    				}
	    				/*if (a.target >= 0 && a.target<ods.length) {
	    				if (ods[a.target].group < grid.gridPoints[pixx][pixy].visibilityO.length)
	    					grid.gridPoints[pixx][pixy].visibilityO[ods[a.target].group] += 1;
	    			}*/
	    			}
	    			catch(NullPointerException e) {

	    			}

	    			
	    			grid.gridPoints[pixx][pixy].visibility += 1;  // // 
	   
	          
	    			if (!grid.gridPoints[pixx][pixy].walkable()) break;
	          
	    			/// far pix assessment
	    			//if (cityMap.distance[target[k]][pixx][pixy] >= 0 &&  cityMap.distance[target[k]][pixx][pixy] < currD) {
	    			if (grid.gridPoints[pixx][pixy].dist[a.target] >= 0 && grid.gridPoints[pixx][pixy].dist[a.target] < currD) {
	    				float len = x*x+y*y;
	    				// this is for using a probability function on the line of sight according to its LENGTH
	    				// rather than taking bluntly the longest one!!
	    				possPixs.addElement(new PixRef(pixx,pixy));
	    				weights.addElement(len);
	    			}
	    			//end far pix assessment
	    		}
	    	} //end scanning visual field
	    	//weighted draw on the possible pix according to **lenght of line of sight**
	    	//p.println(possPixs.size());
	    	int index = myMath.WeightedDrawf(weights);
	    	//p.println(k+": "+index);
	    	if (index!=-1) {
	    		PixRef pr = (PixRef)possPixs.elementAt(index);
	    		a.far_px = pr.pixx; a.far_py = pr.pixy;
	    	}
	    }
	}
	
	
	private void centerScene() {

		xoffs = 0-(drawing_minx + (drawing_maxx-drawing_minx)/2.0f);
		yoffs = 0-(drawing_miny + (drawing_maxy-drawing_miny)/2.0f);
		//xoffs = 0-(drawing_minx);
		//yoffs = 0-(drawing_miny);
		
		float x,y;
		if (buildings!=null) {
			for (int i = 0; i < buildings.size(); i++) {
				//p.println("ho");
				buildings.elementAt(i).move(xoffs, yoffs,0);
			}
		}
		if (obstacles!=null) {
			for (int i = 0; i < obstacles.size(); i++) {
				//p.println("ho");
				obstacles.elementAt(i).move(xoffs, yoffs,0);
			}
		}
		if (landmarks!=null) {
			for (int i = 0; i < landmarks.size(); i++) {
				//p.println("ho");
				landmarks.elementAt(i).move(xoffs, yoffs,0);
			}
		}
		if (site!=null) {
		for (int i = 0; i < site.poly.size(); i++) {
			//site.lines.elementAt(i).move(xoffs, yoffs,0);
			site.poly.elementAt(i).add(xoffs, yoffs,0);
		}
		for (int i = 0; i < site.insertionpoints.size(); i++) {
			site.insertionpoints.elementAt(i).add(xoffs, yoffs,0);
		}
		}
		
		
		
		drawing_minx+=xoffs;
		drawing_miny+=yoffs;
		drawing_maxx+=xoffs;
		drawing_maxy+=yoffs;
	}
	
	private void importModules()
	{
		modules = new Vector<Module>();
		
		DXFHandler dxf = new DXFHandler(p);
		dxf.importDXF(modulepath, false);
		
		//p.println(dxf.polys.elementAt(0).faces.elementAt(0).vertices.size());
		Module m = new Module(p, dxf);
		//p.println(m.polys.elementAt(0).faces.elementAt(0).vertices.size());
		modules.addElement(m);
		//p.println(modules.elementAt((0)).polys.elementAt(0).faces.size());
	}
	
	private void importSite()
	{
		drawing_minx = 9999999999.9f;
		drawing_miny = 9999999999.9f;
		drawing_maxx = -9999999999.9f;
		drawing_maxy = -9999999999.9f;
		
		site = new Site(p);
		
		DXFHandler dxf = new DXFHandler(p);
		dxf.importDXF(sitepath, true);
		
		//p.println(dxf.polys.size());
		float x1,y1;
		if (dxf.polys.size()>0) {
			DXFPoly poly = dxf.polys.elementAt(0);
			poly.scale(scaler);
			if (poly.faces.size()>0) {
				DXFFace face = poly.faces.elementAt(0);
				for (int i = 0; i < face.vertices.size(); i++) {
					x1 = (float)face.vertices.elementAt(i).x ;//* scaler;
					y1 = (float)face.vertices.elementAt(i).y; //* scaler;
					site.poly.addElement(new PVector(x1, y1));
					
					if (x1<drawing_minx) drawing_minx=x1;
					if (y1<drawing_miny) drawing_miny=y1;
					if (x1>drawing_maxx) drawing_maxx=x1;
					if (y1>drawing_maxy) drawing_maxy=y1;
				}
			}
		}
		//p.println(dxf.lwpolys.size());
		if (dxf.lwpolys.size()>0) {
			DXFLWPoly poly = dxf.lwpolys.elementAt(0);
			poly.scale(scaler);
			//if (poly.faces.size()>0) {
				//DXFFace face = poly.faces.elementAt(0);
				for (int i = 0; i < poly.vertices.size(); i++) {
					x1 = (float)poly.vertices.elementAt(i).x;//* scaler;
					y1 = (float)poly.vertices.elementAt(i).y;//* scaler;
					site.poly.addElement(new PVector(x1, y1));
					
					if (x1<drawing_minx) drawing_minx=x1;
					if (y1<drawing_miny) drawing_miny=y1;
					if (x1>drawing_maxx) drawing_maxx=x1;
					if (y1>drawing_maxy) drawing_maxy=y1;
				//}
			}
		}
	}
	
	private void inportLandmarks()
	{
		landmarks = new Vector<Landmark>();
		for (int jj = 0; jj < landmarkpath.length; jj++) {
			DXFHandler dxf = new DXFHandler(p);
			dxf.importDXF(landmarkpath[jj], false);
			
			//p.println(dxf.lwpolys.size());
			//p.println(dxf.polys.size());
			//p.println(dxf.lines.size());
			
	
			Landmark b = new Landmark(p, this);
			// polys - for geometry
			b.setPolys(dxf.polys);
			// lines - for nicer display
			for (int i = 0; i < dxf.lines.size(); i ++) {
				DXFLine l = dxf.lines.elementAt(i);
				if (l.layer.equals("LANDMARK_LINES")) {
					b.lines.addElement(l);
				}
			}// footprint - for economic detection
			for(int i = 0; i < dxf.lwpolys.size(); i++) {
				DXFLWPoly lwpoly = dxf.lwpolys.elementAt(i);
				//p.println(i+" "+lwpoly.layer);
				if (lwpoly.layer.equals("FOOTPRINT")) {
					Footprint foot = new Footprint(p);
					for (int k = 0; k < lwpoly.vertices.size(); k++) {
						DXFVertex v = lwpoly.vertices.elementAt(k);
						foot.addVertex((float)v.x,  (float)v.y, (float)v.z);
					}
					b.footprints.addElement(foot);
				}
			}
			landmarks.addElement(b);
		}
		
	}
	
	void importObstacles()
	{
		obstacles = new Vector<Building>();
		
		DXFHandler dxf = new DXFHandler(p);
		dxf.importDXF(obstaclespath, false);
		
		//p.println(dxf.lwpolys.size());
		for(int i = 0; i < dxf.lwpolys.size(); i++) {
			DXFLWPoly lwpoly = dxf.lwpolys.elementAt(i);
			lwpoly.scale(scaler);
			//p.println(lwpoly.layer);
			Building b = new Building(p, this, 1, "obstacle", lwpoly.layer);
			b.height = 0;
			
			for (int k = 0; k < lwpoly.vertices.size(); k++) {
				DXFVertex v = lwpoly.vertices.elementAt(k);
				b.footprint.addVertex((float)v.x,  (float)v.y, (float)v.z);
			}
			b.fixPolygonVertexOrder();
			obstacles.addElement(b);
		}
		for(int i = 0; i < dxf.polys.size(); i++) {
			DXFPoly poly = dxf.polys.elementAt(i);
			poly.scale(scaler);
			//p.println(lwpoly.layer);
			Building b = new Building(p, this, 1, "obstacle", poly.layer);
			b.height = 0;
			
			for (int k = 0; k < poly.vertices.size(); k++) {
				DXFVertex v = poly.vertices.elementAt(k);
				b.footprint.addVertex((float)v.x,  (float)v.y, (float)v.z);
			}
			b.fixPolygonVertexOrder();
			obstacles.addElement(b);
		}
	}

	void importBuildings() {
		
		// autocad mesh from 3Dsolid
		// MESHOPTIOBNS : choose 'trinagle'
		// CONVTOMESH
		buildings = new Vector<Building>();
		
		DXFHandler dxf = new DXFHandler(p);
		dxf.importDXF(buildingspath, false);
		
		for (int i = 0; i < dxf.meshes.size(); i++) {
			DXFMesh m = dxf.meshes.elementAt(i);
			{
				//p.println("katz "+m.faces.size());
				m.scale(scaler);
				
				m.setMinMaxZValue();
				m.setBottomFaces();
				
				//p.println("   katz "+m.bottomfaces.size());
				
				m.joinBottomFaces();
				
				// for now...
				Building b = new Building(p, this, 1, "building", m.layer);
				b.height = m.maxz - m.minz;
				System.out.println("Mesh footprint size = "+m.footprint.size());
				for (int k = 0; k < m.footprint.size(); k++) {
					DXFVertex v = m.footprint.elementAt(k);
					b.footprint.addVertex((float)v.x,  (float)v.y, (float)v.z);
				}
				b.fixPolygonVertexOrder();
				buildings.addElement(b);
				
			}
		}
	}
	
////////////////////////////////////////////////////////////////////////////////////////
////////////////////////////////////////////////////////////////////////////////////////

	public void onPointerDownRuntime(Pointer pointer, boolean navigationKeys, int num_pointers) {
		if (navigationKeys) 	return;
		if (pointer==null) 		return;
		if (!pointer.inited3D) 	return;
		
		if (interaction_mode==mode_OD || interaction_mode==mode_OD_delete || interaction_mode==mode_OD_weight) {
			OD_hitTest(pointer);
		}
		else if (interaction_mode == mode_BD_add) {
			if (pointer.tempPoly == null)
				pointer.tempPoly = new SimplePoly();
			pointer.tempPoly.addVertex(pointer.m_pos3D.x, pointer.m_pos3D.y, pointer.m_pos3D.z);
		}
		else if (interaction_mode == mode_BD_edit) {
			Building_hitTest(pointer, true, buildings);
			if (pointer.selectedVertexRef != null)
				user_startDragVertex(pointer, buildings);
		}
		else if (interaction_mode == mode_BD_move) {
			Building_hitTest(pointer, false, buildings);
			if (pointer.selectedBuilding != null)
				user_startDragBuilding(pointer);
		}
		else if (interaction_mode == mode_BD_delete) {
			Building_hitTest(pointer, false, buildings);
		}
		else if (interaction_mode == mode_OB_add) {
			if (pointer.tempPoly == null)
				pointer.tempPoly = new SimplePoly();
			pointer.tempPoly.addVertex(pointer.m_pos3D.x, pointer.m_pos3D.y, pointer.m_pos3D.z);
		}
		else if (interaction_mode == mode_OB_edit) {
			Building_hitTest(pointer, true, obstacles);
			if (pointer.selectedVertexRef != null)
				user_startDragVertex(pointer, obstacles);
		}
		else if (interaction_mode == mode_OB_move) {
			Building_hitTest(pointer, false, obstacles);
			if (pointer.selectedBuilding != null)
				user_startDragBuilding(pointer);
		}
		else if (interaction_mode == mode_OB_delete) {
			Building_hitTest(pointer, false, obstacles);
		}
		
		// module 
		else if (interaction_mode==mode_MD_add || interaction_mode==mode_MD_move || interaction_mode==mode_MD_rotate || interaction_mode==mode_MD_delete) 
			Module_hitTest(pointer);
	}	

	public void onPointerDragged(Pointer pointer, boolean navigationKeys, int num_pointers) {
		if (navigationKeys) 	return;
		if (pointer==null) 		return;
		if (!pointer.inited3D) 	return;
		
		if (interaction_mode==mode_OD) {
			if (pointer.selectedOD!=null) {
				user_dragOD(pointer);
			}
		}
		else if (interaction_mode==mode_OD_weight) {
			if (pointer.selectedOD!=null) {
				user_weightOD(pointer);
			}
		}
		
		// building
		else if (interaction_mode==mode_BD_edit) {
			if (pointer.selectedVertexRef!=null) {
				user_dragVertex(pointer, buildings);
			}
			if (pointer.selectedBuilding!=null) {
				user_buildingHeight(pointer);
			}
		}
		else if (interaction_mode==mode_BD_move) {
			if (pointer.selectedBuilding!=null) {
				user_dragBuilding(pointer);
			}
		}
		
		// obstacle
		else if (interaction_mode==mode_OB_edit) {
			if (pointer.selectedVertexRef!=null) {
				user_dragVertex(pointer, obstacles);
			}
			if (pointer.selectedBuilding!=null) {
				user_buildingHeight(pointer);
			}
		}
		else if (interaction_mode==mode_OB_move) {
			if (pointer.selectedBuilding!=null) {
				user_dragBuilding(pointer);
			}
		}
		
		// module
		else if (interaction_mode==mode_MD_rotate) {
			if (pointer.selectedModule!=null) {
				user_rotateModule(pointer);
			}
		}
		
		if (show_iso) {
			if (iso==null)
				iso = new Isovist(p, this, pointer.m_pos3D.x, pointer.m_pos3D.y);
			else
				iso.init(pointer.m_pos3D.x, pointer.m_pos3D.y);
		}
	}


	public void onPointerUp(Pointer pointer, boolean navigationKeys, int num_pointers) {
		if (pointer==null) 		return;
		if (!pointer.inited3D) 	return;
		
		if (!navigationKeys) 	{
			if (interaction_mode==mode_OD) {
				if (pointer.selectedOD==null)
					user_insertOD(pointer);
				else 
					pointer.selectedOD.processed = false; // redo the floodfill of this one
				pointer.selectedOD=null;
			}
			if (interaction_mode==mode_OD_delete) {
				if (pointer.selectedOD!=null) {
					user_deleteOD(pointer);
				}
			}
			// building
			else if (interaction_mode == mode_BD_add) {
				float tol2 = 10;
				if (pointer.tempPoly == null)
					pointer.tempPoly = new SimplePoly();
				//pointer.tempPoly.addVertex(pointer.m_pos3D.x, pointer.m_pos3D.y, pointer.m_pos3D.z);
				if (pointer.tempPoly.vertices.size()>1) {
					float x1 = pointer.tempPoly.vertices.elementAt(0).x;
					float y1 = pointer.tempPoly.vertices.elementAt(0).y;
					float x2 = pointer.tempPoly.vertices.lastElement().x;
					float y2 = pointer.tempPoly.vertices.lastElement().y;
					if (Math.abs(x1-x2) < tol2 && Math.abs(y1-y2) < tol2) {
						user_insertBuildingObstacle(pointer.tempPoly.vertices, 1, 10, "building", "");
						pointer.tempPoly = null;
						/*Building b = new Building(p, this, 1, "building", "");
						b.height = 10;
						for (int k = 0; k < pointer.tempPoly.vertices.size()-1; k++) {  // note not adding the last vertex
							PVector v = pointer.tempPoly.vertices.elementAt(k);
							b.footprint.addVertex(v.x,  v.y, v.z);
						}
						b.fixPolygonVertexOrder();
						buildings.addElement(b);
						partialGridUpdater.addElement(new rect(	b.footprint.minX,
								b.footprint.minY,
								b.footprint.maxX,
								b.footprint.maxY));
						pointer.tempPoly = null;*/
					}
				}
			}
			else if (interaction_mode==mode_BD_edit) {
				if (pointer.selectedVertexRef!=null) {
					user_endDragVertex(pointer, buildings);
				}
				else {
					if (pointer.selectedBuilding==null)
						user_onPolySplit(pointer, buildings);
				}
			}
			else if (interaction_mode==mode_BD_move) {
				if (pointer.selectedBuilding!=null) {
					user_endDragBuilding(pointer);
				}
			}
			else if (interaction_mode==mode_BD_delete) {
				if (pointer.selectedBuilding!=null) {
					user_deleteBuilding(pointer, buildings);
				}
			}
			
			// obstacle
			// building
			else if (interaction_mode == mode_OB_add) {
				float tol2 = 10;
				if (pointer.tempPoly == null)
					pointer.tempPoly = new SimplePoly();
				//pointer.tempPoly.addVertex(pointer.m_pos3D.x, pointer.m_pos3D.y, pointer.m_pos3D.z);
				if (pointer.tempPoly.vertices.size()>1) {
					float x1 = pointer.tempPoly.vertices.elementAt(0).x;
					float y1 = pointer.tempPoly.vertices.elementAt(0).y;
					float x2 = pointer.tempPoly.vertices.lastElement().x;
					float y2 = pointer.tempPoly.vertices.lastElement().y;
					if (Math.abs(x1-x2) < tol2 && Math.abs(y1-y2) < tol2) {
						user_insertBuildingObstacle(pointer.tempPoly.vertices, 1, 1, "obstacle", "OBSTACLES_LOW");
						pointer.tempPoly = null;
					}
				}
			}
			else if (interaction_mode==mode_OB_edit) {
				if (pointer.selectedVertexRef!=null) {
					user_endDragVertex(pointer, obstacles);
				}
				else {
					if (pointer.selectedBuilding==null)
						user_onPolySplit(pointer, obstacles);
				}
			}
			else if (interaction_mode==mode_OB_move) {
				if (pointer.selectedBuilding!=null) {
					user_endDragBuilding(pointer);
				}
			}
			else if (interaction_mode==mode_OB_delete) {
				if (pointer.selectedBuilding!=null) {
					user_deleteBuilding(pointer, obstacles);
				}
			}
			// module 
			else if (interaction_mode==mode_MD_add) 
				user_insertModule(pointer, modules.elementAt(0));
			
		}
		if (iso!=null) iso = null;
	}
	
	private void user_insertBuildingObstacle(Vector <PVector> vertices, int floors, float height, String type, String layer)
	{
		
		Building b = new Building(p, this, floors, type, layer);
		b.height = height;
		for (int k = 0; k < vertices.size()-1; k++) {  // note not adding the last vertex
			PVector v = vertices.elementAt(k);
			b.footprint.addVertex(v.x,  v.y, v.z);
		}
		b.fixPolygonVertexOrder();
		if (type.equals("building"))
			buildings.addElement(b);
		else
			obstacles.addElement(b);
		partialGridUpdater.addElement(new rect(	b.footprint.minX,
				b.footprint.minY,
				b.footprint.maxX,
				b.footprint.maxY));
		
	}
	
	///////////////////////////////////////////////////////////////////////////////
	// module
	private void user_insertModule(Pointer pointer, Module M) {
		if (pointer.m_pos3D == null ) 	return;
		Module mod = new Module(M, pointer.m_pos3D);
		mod.snap(site.insertionpoints);
		placedModules.addElement(mod);
	}
	
	private void user_rotateModule(Pointer pointer) {
		if (pointer.m_pos3D == null || pointer.m_ppos3D == null || pointer.m_fpos3D == null) 	return;
		pointer.selectedModule.rotate(pointer);
	}
	
	///////////////////////////////////////////////////////////////////////////////
	// building
	
	

	private void user_startDragVertex(Pointer pointer, Vector<Building> polygonals) {
		int[] arr = pointer.selectedVertexRef;
		if (arr==null) 												return;
		if (arr[0]<0 || arr[0]>= polygonals.size()) 					return;
		
		polygonals.elementAt(arr[0]).footprint.boundingToPreviousBoundingRectangle();
		polygonals.elementAt(arr[0]).vertexdragged = true;
		
	}
	private void user_dragVertex(Pointer pointer, Vector<Building> polygonals)
	{
		if (pointer.m_pos3D == null || pointer.m_ppos3D == null) 	return;
		
		int[] arr = pointer.selectedVertexRef;
		if (arr==null) 												return;
		if (arr[0]<0 || arr[0]>= polygonals.size()) 					return;
		if (arr[1]<0 || arr[1]>= polygonals.elementAt(arr[0]).footprint.vertices.size()) 
																	return;
		
		PVector v = new PVector(pointer.m_pos3D.x-pointer.m_ppos3D.x,
								pointer.m_pos3D.y-pointer.m_ppos3D.y, 
								0);
		polygonals.elementAt(arr[0]).footprint.vertices.elementAt(arr[1]).add(v);
	}
	
	private void user_endDragVertex(Pointer pointer, Vector<Building> polygonals) {
		int[] arr = pointer.selectedVertexRef;
		if (arr==null) 												return;
		if (arr[0]<0 || arr[0]>= polygonals.size()) 					return;
		
		polygonals.elementAt(arr[0]).fixPolygonVertexOrder();
		
		polygonals.elementAt(arr[0]).vertexdragged = false;
		polygonals.elementAt(arr[0]).footprint.setBoundingRectangle();
		polygonals.elementAt(arr[0]).footprint.needs_updateGridSegments = true;
		partialGridUpdater.addElement(new rect(	PApplet.min(polygonals.elementAt(arr[0]).footprint.minX,polygonals.elementAt(arr[0]).footprint.pminX),
												PApplet.min(polygonals.elementAt(arr[0]).footprint.minY,polygonals.elementAt(arr[0]).footprint.pminY),
												PApplet.max(polygonals.elementAt(arr[0]).footprint.maxX,polygonals.elementAt(arr[0]).footprint.pmaxX),
												PApplet.max(polygonals.elementAt(arr[0]).footprint.maxY,polygonals.elementAt(arr[0]).footprint.pmaxY)));
	}
	
	private void user_onPolySplit(Pointer pointer, Vector<Building> polygonals) {
		//security //
		  if (pointer == null) return; 
		  if (pointer.m_fpos3D==null) return; if (pointer.m_pos3D==null) return;
		  //security //
		  
		//test if the dragged pointer has intersected a polygon
		  Vector<PolySplitInfo> polySplitList = new Vector<PolySplitInfo> ();
		  for (int i = 0; i < polygonals.size(); i++) 
		  {
		    Building B = polygonals.elementAt(i);
		    PolySplitInfo splitInfo = new PolySplitInfo();
		    
		    //getIntersectionsWithPoly(p.vertices, (int)P.fx3D, (int)P.fy3D, (int)P.x3D, (int)P.y3D, P.intersections, P.vertices);
		    MyMath.LinePolyIntersectons(B.footprint.vertices, pointer.m_fpos3D.x, pointer.m_fpos3D.y, pointer.m_pos3D.x, pointer.m_pos3D.y, splitInfo.intersections, splitInfo.vertices);

		    if (splitInfo.intersections.size() == 2) {
		      splitInfo.poly = B;
		      polySplitList.add(splitInfo);
		    }
		  }
		//p.println(polySplitList.size());
		  if (polySplitList.size() == 0) return;
		  
		  for (int i = 0; i < polySplitList.size(); i++) {
		    PolySplitInfo splitInfo = polySplitList.elementAt(i);
		    if (splitInfo.poly == null) continue;
		    
		    
		    
		    //split the polygons, p gets replaced by p1 and p2
		    Vector<PVector> foot1 = new Vector<PVector>();
		    Vector<PVector> foot2 = new Vector<PVector>();
		    MyMath.splitPolygon(splitInfo.poly.footprint.vertices, foot1, foot2, splitInfo.intersections, splitInfo.vertices);
		    
		    // make 2 new polys
		    Building p1 = new Building(splitInfo.poly);                                    //a pointer to the new polygons
		    Building p2 = new Building(splitInfo.poly);
		    p1.footprint.setVertices(foot1);
		    p2.footprint.setVertices(foot2);
		    
		    //clean the polygon, if necessary
		    p1.fixPolygonVertexOrder();
		    p2.fixPolygonVertexOrder();
		    
		    //calculate the facade segs that are used for display of the facade visibility
		    p1.footprint.calculateGriddedSegments(this);
		    p2.footprint.calculateGriddedSegments(this);
		    
		    polygonals.addElement(p1);
		    polygonals.addElement(p2);
		    
		    // remove old poly
		    polygonals.remove(splitInfo.poly);
		    
		    
		  }
	}
	
	private void user_buildingHeight(Pointer pointer)
	{
		float a = PApplet.abs(pointer.m_screen.y - pointer.m_pscreen.y);
		if (a < 2) return;
		if (pointer.m_screen.y < pointer.m_pscreen.y) 
			pointer.selectedBuilding.height+=6;
		else
			pointer.selectedBuilding.height-=6;
		if (pointer.selectedBuilding.height<0) pointer.selectedBuilding.height=0;
	}
	
	private void user_startDragBuilding(Pointer pointer) {
		pointer.selectedBuilding.footprint.boundingToPreviousBoundingRectangle();
	}
	private void user_dragBuilding(Pointer pointer)
	{
		if (pointer.m_pos3D == null || pointer.m_ppos3D == null) return;
		
		pointer.selectedBuilding.move(  pointer.m_pos3D.x-pointer.m_ppos3D.x, 
				 						pointer.m_pos3D.y-pointer.m_ppos3D.y, 
				 						0);
	}
	
	private void user_endDragBuilding(Pointer pointer) {
		pointer.selectedBuilding.footprint.needs_updateGridSegments = true;
		pointer.selectedBuilding.footprint.setBoundingRectangle();
		partialGridUpdater.addElement(new rect(	PApplet.min(pointer.selectedBuilding.footprint.minX,pointer.selectedBuilding.footprint.pminX),
												PApplet.min(pointer.selectedBuilding.footprint.minY,pointer.selectedBuilding.footprint.pminY),
												PApplet.max(pointer.selectedBuilding.footprint.maxX,pointer.selectedBuilding.footprint.pmaxX),
												PApplet.max(pointer.selectedBuilding.footprint.maxY,pointer.selectedBuilding.footprint.pmaxY)));
	}
	
	private void user_deleteBuilding(Pointer pointer, Vector<Building> polygonals)
	{
		partialGridUpdater.addElement(new rect(	pointer.selectedBuilding.footprint.minX,
												pointer.selectedBuilding.footprint.minY,
												pointer.selectedBuilding.footprint.maxX,
												pointer.selectedBuilding.footprint.maxY));
		polygonals.remove(pointer.selectedBuilding);
	}
	
	private void Module_hitTest(Pointer pointer)
	{

		for (int i = 0; i < placedModules.size(); i++) {
			Module b = placedModules.elementAt(i);
			boolean res = false;
			for (int k = 0; k < b.foot_untransformed.size(); k++) {
				boolean hit = b.foot_untransformed.elementAt(k).hitTestS((int)pointer.m_screen.x, (int)pointer.m_screen.y);
				if (hit) { res = true; break; } 
			}
	
			if (res) {
				pointer.selectedModule = b;
				return;
			}
		}
		// for now
		//pointer.selectedModule = placedModules.elementAt(0);
		pointer.selectedModule = null;
	}
	
	
	private void Building_hitTest(Pointer pointer, boolean checkVertexHit, Vector<Building> polygonals)
	{
		Building b;
		pointer.selectedVertexRef = null;
		pointer.selectedBuilding = null;
		
		// check if we have hit a vertex //////////////////////////////////////////
		if (checkVertexHit) { 
			Vector<int[]> hitVertices = new Vector<int[]>();
			
			for (int i = 0; i < polygonals.size(); i++) {
				b = polygonals.elementAt(i);
				b.footprint.vertexHitTestS((int)pointer.m_screen.x, (int)pointer.m_screen.y, i, hitVertices);
			}
			//p.println(hitVertices.size());
			if (hitVertices.size()>0) {
				// find the nearest amd stick into pointer
				float d = 10;
				int arr[];
				PVector pos;
				for (int i = 0; i < hitVertices.size(); i++) {
					arr = hitVertices.elementAt(i);
					if (arr[0] >= 0 && arr[0] < polygonals.size()) {
						if (arr[1] >= 0 && arr[1] < polygonals.elementAt(arr[0]).footprint.verticesS.size()) {
							pos = polygonals.elementAt(arr[0]).footprint.verticesS.elementAt(arr[1]);
							if (pos.z < d) {
								d = pos.z;
								pointer.selectedVertexRef = arr;
							}
						}
					}
				}
				return;
			}
		}
		
		// check if we have clicked into the footprint of a building ///////////////////
		for (int i = 0; i < polygonals.size(); i++) {
			b = polygonals.elementAt(i);
			boolean res = b.footprint.hitTestS((int)pointer.m_screen.x, (int)pointer.m_screen.y);
			if (res) {
				pointer.selectedBuilding = b;
				//PApplet.println(i);
				return;
			}
		}
	}
	
	////////////////////////////////////////////////////////////////////////////////
	// od
	
	private void OD_hitTest(Pointer pointer){
		OD od;
		pointer.selectedOD = null;
		for (int i = 0; i < ods.length; i++) {
			if (ods[i]==null) continue;
			od = ods[i];
			if (od.posS.z > 0.99) continue;  // not a valid screen coord
			if (od.posS.z < 0   ) continue;
			if (od.posS.x < (pointer.m_screen.x-tol)) continue;
			if (od.posS.y < (pointer.m_screen.y-tol)) continue;
			if (od.posS.x > (pointer.m_screen.x+tol)) continue;
			if (od.posS.y > (pointer.m_screen.y+tol)) continue;
			//p.println("hit");
			pointer.selectedOD = od;
			return;
		}
	}
	
	private void user_dragOD(Pointer pointer) 
	{
		if (pointer.selectedOD==null) return;
		if (pointer.m_pos3D   ==null) return;
		if (pointer.m_ppos3D  ==null) return;
		pointer.selectedOD.pos.x+=(pointer.m_pos3D.x-pointer.m_ppos3D.x);
		pointer.selectedOD.pos.y+=(pointer.m_pos3D.y-pointer.m_ppos3D.y);
	}
	
	private void user_weightOD(Pointer pointer) {
		if (pointer.selectedOD==null) return;
		if (pointer.selectedOD.posS == null) return;
		
		if (pointer.selectedOD.posS.y > pointer.m_fscreen.y ) pointer.selectedOD.weightO(pointer.m_screen.y-pointer.m_pscreen.y); //oWeight += 0.1f;
		else pointer.selectedOD.weightD(pointer.m_screen.y-pointer.m_pscreen.y);
	}
	
	private void user_insertOD(Pointer pointer) {
		//if (ods.size() >= max_num_OD) return;
		int k = -1;
		
		for (int i = 0; i < ods.length; i++) {
			if (ods[i] == null) { k=i; break; }
		}
		if (k==-1) return;
		ods[k] = new OD(p, pointer.m_pos3D.x, pointer.m_pos3D.y, 0, 0);
	}
	
	private void user_deleteOD(Pointer pointer) {
		if (pointer.selectedOD==null) return;
		//this.ods.remove(pointer.selectedOD);
		for (int i = 0; i < ods.length; i++) {
			if (ods[i] == null) continue;
			if (ods[i] == pointer.selectedOD) {
				ods[i] = null; return;
			}
		}
	}

	

	/////////////////////////////////////////////////////////////////////////////////

}


