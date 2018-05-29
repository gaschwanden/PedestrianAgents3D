import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.File;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.Vector;

import javax.swing.JFileChooser;

import processing.core.PApplet;
import processing.core.PVector;
import utility.MyMath;


public class Grid_Thread implements Runnable {
	Thread t;
	Scene scene;
	int release_rate = 10;
	MyMath myMath;
	int counter=0;
	
	public Grid_Thread( Scene s , PApplet _p)
	{
		scene = s;
		t = new Thread(this, "Demo Thread");
	    //System.out.println("Child thread: " + t);
	    t.start(); // Start the thread
	    myMath = new MyMath(_p);
	}

	@Override
	public void run() {
		while(true) {
			//counter++;
			//System.out.println(counter);
			if (scene.notifyAppRenew == true) {
				scene.init();
				scene.resetView();
				continue;
			}
			if (scene.notifyLoadObstacles == true) {
				loadObstacles();
				continue;
			}
			if (scene.notifyLoadBuildings == true) {
				loadBuildings();
				continue;
			}
			if (scene.notifyLoadODs == true) {
				loadODs();
				continue;
			}
			if (scene.notifySaveODs == true) {
				saveODs();
				continue;
			}
			// reset analysis? // this is when we have stopped the agents altogether - need to reset all the parcels
			if (scene.needsAnalysisReset) {
				resetAnalysis();
				continue;
			}
			//check if we need to update and facade grid segemnts - when we have moved a building
			updateFacadeGrid();
			// check if we need to update parts of the grid in terms of solidity - if a building has moved or changed
			partialGridStatus();
			//PApplet.println(scene.ods.size());
			boolean updated = updateFloodfill();
			if (updated) continue;
			// check if we can initialise agents
			addAgents();
			
			if (scene.iso!=null) scene.iso.make();
		}
		
		//PApplet.println("finished");
	}
	
	private void updateFacadeGrid()
	{
		if (scene.buildings!=null) {
			for (int i = 0; i < scene.buildings.size(); i++) {
				try {
					if (scene.buildings.elementAt(i).footprint.needs_updateGridSegments)
						scene.buildings.elementAt(i).footprint.calculateGriddedSegments(scene);
				}
				catch (ArrayIndexOutOfBoundsException e){
				    //System.out.println("This page  can't be read");
			    }    
			}
		}
	}
	
	private void resetAnalysis() {
		//System.out.println("katz");
		
		for (int i = 0; i < scene.grid.gridPoints.length; i++ ) {
			for (int j = 0; j < scene.grid.gridPoints[i].length; j++ ) {
				
				scene.grid.gridPoints[i][j].occupancy = 0;
				scene.grid.gridPoints[i][j].visibility = 0;
				for (int k = 0; k < scene.grid.gridPoints[i][j].visibilityO.length; k++) {
					scene.grid.gridPoints[i][j].visibilityO[k]=0;
				}
			}
		}
		scene.agents.clear();
		for (int i = 0; i < scene.agents.size(); i++) {
			scene.agents.elementAt(i).active = false;
		}
		scene.traces = new Vector<Trace>();
		
		scene.needsAnalysisReset = false;
	}
	
	private void loadBuildings()
	{
		JFileChooser FC = new JFileChooser();
		File theDirectory = new File(scene.folderpath);
		FC.setCurrentDirectory(theDirectory);
		int retval = FC.showOpenDialog(scene.p);
		
		if (retval == JFileChooser.APPROVE_OPTION) {
			File file = FC.getSelectedFile();
			scene.buildingspath = file.getAbsolutePath();
		
			scene.importBuildings();
			if (scene.obstacles!=null) {
				for (int i = 0; i < scene.buildings.size(); i++) {
					//p.println("ho");
					scene.buildings.elementAt(i).move(scene.xoffs, scene.yoffs,0);
				}
			}
		}
		scene.notifyLoadBuildings = false;
	}
	
	private void loadObstacles()
	{
		JFileChooser FC = new JFileChooser();
		File theDirectory = new File(scene.folderpath);
		FC.setCurrentDirectory(theDirectory);
		int retval = FC.showOpenDialog(scene.p);
		
		if (retval == JFileChooser.APPROVE_OPTION) {
			File file = FC.getSelectedFile();
			scene.obstaclespath = file.getAbsolutePath();
		
			scene.importObstacles();
			if (scene.obstacles!=null) {
				for (int i = 0; i < scene.obstacles.size(); i++) {
					//p.println("ho");
					scene.obstacles.elementAt(i).move(scene.xoffs, scene.yoffs,0);
				}
			}
		}
		scene.notifyLoadObstacles = false;
	}
	
	public void loadODs()
	{
		for (int i = 0; i < scene.ods.length; i++) {
			scene.ods[i]=null;
		}
		
		JFileChooser FC = new JFileChooser();
		File theDirectory = new File(scene.folderpath);
		FC.setCurrentDirectory(theDirectory);
		int retval = FC.showOpenDialog(scene.p);
		
		if (retval == JFileChooser.APPROVE_OPTION) {
			File file = FC.getSelectedFile();
			
			BufferedReader br;
			String text;
			try {
				br=new BufferedReader(new FileReader(file.getAbsolutePath()));
			} catch (FileNotFoundException e1) {
				e1.printStackTrace();
				return;
			}
		    int odcounter = 0;
		    try {
				while((text=br.readLine())!=null){
					//p.println(text);
					String s[] = text.split(",");
					if (s.length>0) {
						if (s[0].equals("OD")) {
							if (s.length < 6) continue;
							
							float x = Float.parseFloat(s[1]);
							float y = Float.parseFloat(s[2]);
							float z = Float.parseFloat(s[3]);
							float ow = Float.parseFloat(s[4]);
							float dw = Float.parseFloat(s[5]);
							int group = 0;
							if (s.length > 6)
								group = Integer.parseInt(s[6]);
							
							if (odcounter < scene.ods.length) {
								OD od = new OD(scene.p, x,y,z,group);
								od.oWeight = ow;
								od.dWeight = dw;
								scene.ods[odcounter] = od;
								odcounter++;
							}
						}
					}
				}
			}
		    catch (IOException e) {
				e.printStackTrace();
			}
		}
		
		scene.notifyLoadODs = false;
	}
	
	public void loadODs(String oDPath) {
		for (int i = 0; i < scene.ods.length; i++) {
			scene.ods[i]=null;
		}
		
//		JFileChooser FC = new JFileChooser();
//		File theDirectory = new File(scene.folderpath);
//		FC.setCurrentDirectory(theDirectory);
//		int retval = FC.showOpenDialog(scene.p);
		
//			File file = FC.getSelectedFile();
			
			BufferedReader br;
			String text;
			try {
				br=new BufferedReader(new FileReader(oDPath));
			} catch (FileNotFoundException e1) {
				e1.printStackTrace();
				return;
			}
		    int odcounter = 0;
		    try {
				while((text=br.readLine())!=null){
					//p.println(text);
					String s[] = text.split(",");
					if (s.length>0) {
						if (s[0].equals("OD")) {
							if (s.length < 6) continue;
							
							float x = Float.parseFloat(s[1]);
							float y = Float.parseFloat(s[2]);
							float z = Float.parseFloat(s[3]);
							float ow = Float.parseFloat(s[4]);
							float dw = Float.parseFloat(s[5]);
							int group = 0;
							if (s.length > 6)
								group = Integer.parseInt(s[6]);
							
							if (odcounter < scene.ods.length) {
								OD od = new OD(scene.p, x,y,z,group);
								od.oWeight = ow;
								od.dWeight = dw;
								scene.ods[odcounter] = od;
								odcounter++;
								System.out.println("loaded "+odcounter+" ODs");
							}
						}
					}
				}
			}
		    catch (IOException e) {
				e.printStackTrace();
			}
		
		System.out.println("loaded OD at"+oDPath);
		scene.notifyLoadODs = false;
	}
	
	private void saveODs()
	{
		if (scene.ods.length == 0) return;
		JFileChooser FC = new JFileChooser();
		File theDirectory = new File(scene.folderpath);
		FC.setCurrentDirectory(theDirectory);
		int retval = FC.showSaveDialog(scene.p);
		
		if (retval == JFileChooser.APPROVE_OPTION) {
			File file = FC.getSelectedFile();
			
			String filePath = file.getPath();
			if(!filePath.toLowerCase().endsWith(".txt"))
			{
			    file = new File(filePath + ".txt");
			}
			
			try
			{
			    BufferedWriter writer = new BufferedWriter(new FileWriter(file));
			    for (int i = 0; i < scene.ods.length; i++) {
			    	if (scene.ods[i] == null) continue;
			    	writer.write("OD,"+scene.ods[i].pos.x+","+scene.ods[i].pos.y+","+scene.ods[i].pos.z+","+scene.ods[i].oWeight+","+scene.ods[i].dWeight+"\n");
			    	
			    	//writer.write ("END\n");
			    }
			   // writer.write ("END\n");
			  

			    //Close writer
			    writer.close();
			} catch(Exception e)
			{
			    e.printStackTrace();
			}
		}
		
		scene.notifySaveODs = false;
	}
	
	private void partialGridStatus()
	{
		if (scene.partialGridUpdater.size()>0) {
			// we need to tell all the ods they need to update after grid updating is finished
			for (int i = 0; i < scene.ods.length; i++) {
				OD od = scene.ods[i];
				if (od==null) continue;
				od.processed = false;
			}
		}
		// now update
		while (scene.partialGridUpdater.size()>0) {
			rect R = scene.partialGridUpdater.elementAt(0);
			partialGridStatus(R.minx,R.miny,R.maxx,R.maxy);
			scene.partialGridUpdater.remove(0);
		}
	}
	
	private void partialGridStatus(float _minx,float _miny,float _maxx,float _maxy) {
		//System.out.println(_minx+" "+ _miny+" "+ _maxx+" "+_maxy);
		int minpx = scene.grid.getGridcellX(_minx);
	    int minpy = scene.grid.getGridcellY(_miny);
	    int maxpx = scene.grid.getGridcellX(_maxx);
	    int maxpy = scene.grid.getGridcellY(_maxy);
	    
	    if (minpx<0) minpx=0; if (minpx>=scene.grid.gridPoints.length) 		minpx = scene.grid.gridPoints.length-1;
	    if (minpy<0) minpy=0; if (minpy>=scene.grid.gridPoints[0].length) 	minpy = scene.grid.gridPoints[0].length-1;
	    if (maxpx<0) minpx=0; if (maxpx>=scene.grid.gridPoints.length) 		maxpx = scene.grid.gridPoints.length-1;
	    if (maxpy<0) minpy=0; if (maxpy>=scene.grid.gridPoints[0].length) 	maxpy = scene.grid.gridPoints[0].length-1;
		
		
		for (int i = minpx; i < maxpx+1; i++) {
			for (int j = minpy; j < maxpy+1; j++) {
				scene.grid.gridPoints[i][j].openspace = true;
				scene.grid.gridPoints[i][j].boundary = false;
			}
		}
	    int pnum = -1;
	    
	    //boolean extracheck = false;
	    for (int x = minpx; x < maxpx+1; x++) {
			for (int y = minpy; y < maxpy+1; y++) {
				pnum = scene.grid.pointObstructed(scene.buildings, scene.grid.sx + x*scene.grid.gridsize,scene.grid.sy + y*scene.grid.gridsize);  //there can be many on top of each other, check if there is one on the floor!
				if (pnum != -1) 
				{ 
					scene.grid.gridPoints[x][y].openspace = false;
				}
				else {
					pnum = scene.grid.pointObstructed(scene.obstacles, scene.grid.sx + x*scene.grid.gridsize,scene.grid.sy + y*scene.grid.gridsize);  //there can be many on top of each other, check if there is one on the floor!
					if (pnum != -1) 
					{ 
						scene.grid.gridPoints[x][y].openspace = false;
					}
				}
			}
	    }
	    // set boundary
	    for (int x = 0; x < scene.grid.gridPoints.length; x++) {
			for (int y = 0; y < scene.grid.gridPoints[x].length; y++) {
				if (!scene.grid.gridPoints[x][y].openspace) {
					boolean b = false;
					for (int k = x-1; k < x+2; k++) {
						for (int kk = y-1; kk < y+2; kk++) {
							if (k==0&&kk==0) continue;
							if (k>0&&k<scene.grid.gridPoints.length) {
								if (kk>0&&kk<scene.grid.gridPoints[k].length) {
									if (scene.grid.gridPoints[k][kk].openspace==true) b = true;
								}
							}
						}
					}
					if (b==true) scene.grid.gridPoints[x][y].boundary = true;
					
				}
			}
		}
	}
	
	/*private int pointObstructed(Vector<Building> buildings, float x, float y) {
		for (int i = 0; i < buildings.size(); i++)
		{
		    Building p = buildings.elementAt(i);
		    if (p == null) continue;
		    if (p.footprint.vertices == null) continue;
		    if (p.footprint.vertices.size() == 0) continue;
		    if (p.footprint.vertices.elementAt(0).z >0.1) continue;
		    
		    //test against bounding rectangle
		    if (x<p.footprint.minX || y<p.footprint.minY || x>p.footprint.maxX || y>p.footprint.maxY) continue;
		    
		    //if ( p.pointInside(x,y, p.vertices)) return i;
		    if (myMath.pointInPoly(x, y, p.footprint.vertices)) {
		    	return i;
		    }
		 }
		 return -1;
	}*/
	
	private void addAgents()
	{
		int num = 0;
		for (int i = 0; i < scene.ods.length; i++) {
			if (scene.ods[i] != null) {
				num++;
			}
		}
		if (num>1 && scene.analysis_mode != scene.mode_noInteraction) {
			int released = 0;
			for (int i = 0; i < scene.agents.size(); i++) {
				if (!scene.agents.elementAt(i).active) {
					initAgent(scene.agents.elementAt(i));
					released++;
					if (released>=release_rate) break;
				}
			}
		}
	}

	private void initAgent(Agent a) {
		a.renew();
	}
	
	private boolean updateFloodfill()
	{
		//
		boolean updated = false;
		for (int i = 0; i < scene.ods.length; i++) {
			OD od = scene.ods[i];
			if (od==null) continue;
			if (!od.processed) {
				
				floodfill(i);
				od.processed = true;
				updated = true;
			}
		}
		return updated;
	}

	private void floodfill(int num) {
		// flood fill the map 
		// this uses a queue to keep track of the pixels seen and to iterate from,
		// much faster than the blunt loop one!
		{
			
			int xSize = scene.grid.gridPoints.length;
			int ySize = scene.grid.gridPoints[0].length;
		
		
		    int added[][] = new int[xSize][ySize];
		    int distance[][] = new int[xSize][ySize];

		    Vector queue = new Vector();
		    PVector a = new PVector();
		    
		    //seed
		    if (num >= scene.ods.length) return;

		    OD od = scene.ods[num];   ///// //// //// 
		      
		    // a quick fix to bring targets onto the ground plane............
		    //if (od.pos.x < 0) { od.x = 0; od.px = 0; }
		    //if (od.y < 0) { od.y = 0; od.py = 0; }
		    //if (od.x >= groundplane_size_x) { od.x = groundplane_size_x-1; od.px = xSize-1; }
		    //if (od.y >= groundplane_size_y) { od.y = groundplane_size_y-1; od.py = ySize-1; }
		    //if (od.px >= xSize) {  od.px = xSize-1; od.x = od.px*gridSize; }
		    //if (od.py >= ySize) {  od.py = ySize-1; od.y = od.py*gridSize; }
		    if (od.pos.x < scene.drawing_minx) od.pos.x = scene.drawing_minx;
		    if (od.pos.y < scene.drawing_miny) od.pos.y = scene.drawing_miny;
		    if (od.pos.x > scene.drawing_maxx) od.pos.x = scene.drawing_maxx;
		    if (od.pos.y > scene.drawing_maxy) od.pos.y = scene.drawing_maxy;
		    
		    int px = scene.grid.getGridcellX(od.pos.x);
		    int py = scene.grid.getGridcellY(od.pos.y);
		    
		    if (px<0) px=0; if (px>=scene.grid.gridPoints.length) 		px = scene.grid.gridPoints.length;
		    if (py<0) py=0; if (py>=scene.grid.gridPoints[0].length) 	py = scene.grid.gridPoints[0].length;
		    
		    
		      
		    distance[px][py] = 1;
		    PVector pos = new PVector(px,py,1);  //note we are putting the distance into the z component
		    queue.addElement(pos);
		      
		    int iter = 0;
		    while (queue.size()!=0 ) //&& iter < 3000)
		    {
		      iter++;
		      //System.out.println("flood iteration "+iter);
		      a = (PVector)queue.elementAt(0);

		      int d = (int)a.z;
		      for (int i=-1; i<2; i++) {
		        for (int j=-1; j<2; j++) {
		          
		          if (i==0 && j==0) continue;                            	//it's us
		          // bias towards the rectangular...
		          if (scene.p.random(100) >= 30) {              // quick hack to 'randomise' the flood fill - 
		        	  									  // otherwise it would prefer either the diagonals or the orthogonals
		        	  									  // alternatively, we could use a hexagonal grid...
			          if (i==-1 && j==-1) continue; 
			          if (i==-1 && j==1) continue;
			          if (i==1 && j==-1) continue; 
			          if (i==1 && j==1) continue; 
		          }
		          // end bias
		          int x = (int)a.x+i;
		          int y = (int)a.y+j;   
		         
		          if (x<0 || x >= xSize || y<0 || y >= ySize) continue;  	//not on the ground plane
		          if (!scene.grid.gridPoints[x][y].walkable()) continue;     	//obstructed
		          if (distance[x][y] != 0) continue;                		//already seen
		        
		          //println("    adding "+x+" "+y+" at "+(d+1)+", was "+distance[num][x][y]);
		          distance[x][y] = d+1;
		          //System.out.println("flood iteration "+iter);
		          PVector b = new PVector(x,y,d+1);  //note we are putting the distance into the z component
		          queue.addElement(b);
		        }
		      }
		      queue.remove(0);
		    }

		    // copy over the result
		    for (int i = 0; i < distance.length; i++) {
		    	for (int j = 0; j < distance[i].length; j++) {
		    		scene.grid.gridPoints[i][j].dist[num] = distance[i][j];
		    	}
		    }
		}
		
	}
	

}
