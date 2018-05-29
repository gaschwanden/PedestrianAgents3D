import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import utility.MyMath;


public class Grid {
	
	PApplet p;
	float sx;
	float sy;
	float gridsize;
	
	GridPoint[][] gridPoints;
	
	MyMath myMath;
	
	float maxOccupation = 0;
	float maxVisibility = 0;
	float maxBoundaryVisibility = 0;
	float maxBoundaryVisibilityO = 0;
	float decay = 0.99f;
	
	public Grid(PApplet _p, float drawing_minx, float drawing_miny, float drawing_maxx, float drawing_maxy, float _gridsize, int maxNumOd, Vector<Building>buildings, Vector<Building>obstacles, Vector<PVector>sitepoly) 
	{
		p=_p;
		myMath = new MyMath(p);
		gridsize=_gridsize;
		float dx = drawing_maxx - drawing_minx;
		float dy = drawing_maxy - drawing_miny;
		sx = drawing_minx + gridsize/2.0f;
		sy = drawing_miny + gridsize/2.0f;
		
		gridPoints = new GridPoint[p.ceil(dx/gridsize)][p.ceil(dy/gridsize)];
		
		//for (float x = drawing_minx; x < drawing_maxx; x+= gridsize) {
			//for (float y = drawing_miny; y < drawing_maxy; y+= gridsize) {
		for (int i = 0; i < gridPoints.length; i++) {
			for (int j = 0; j < gridPoints[i].length; j++) {
				gridPoints[i][j] = new GridPoint(this, maxNumOd);
			}
		}
		initGridStatus(buildings, obstacles, sitepoly);
		//p.println(drawing_minx+" "+drawing_miny+" "+drawing_maxx+" "+drawing_maxy);
	}
	
	public void draw(int display_mode) {
		p.pushMatrix();
		p.translate(0, 0,-0.3f);
		p.strokeWeight(2);
		if (display_mode == Scene.display_pathoverlap) {
			for (int i = 0; i < gridPoints.length; i++) {
				for (int j = 0; j < gridPoints[i].length; j++) {
					gridPoints[i][j].drawOccupation(p, i, j);
					//gridPoints[i][j].drawVisibility(p, i, j);
				}
			}
		}
		else {
			/*for (int i = 0; i < gridPoints.length; i++) {
				for (int j = 0; j < gridPoints[i].length; j++) {
					gridPoints[i][j].drawTest(p, i, j);
				}
			}*/
		}
		p.strokeWeight(1);
		p.popMatrix();
		
		decayGridValues();
	}
	
	
	private void decayGridValues() {
		maxOccupation = 0;
		maxVisibility = 0;
		maxBoundaryVisibility = 0;
		maxBoundaryVisibilityO = 0;
		for (int i = 0; i < gridPoints.length; i++) {
			for (int j = 0; j < gridPoints[i].length; j++) {
				//gridPoints[i][j] = new GridPoint();
				if (/*gridPoints[i][j].filled &&*/ gridPoints[i][j].occupancy>0) {
					gridPoints[i][j].occupancy*=decay;
					if (gridPoints[i][j].occupancy < 0.001) gridPoints[i][j].occupancy=0;
					if (maxOccupation<gridPoints[i][j].occupancy) maxOccupation=gridPoints[i][j].occupancy;
				}
				
				for (int k = 0; k < gridPoints[i][j].visibilityO.length; k++) {
					if (gridPoints[i][j].visibilityO[k]>0) {
						gridPoints[i][j].visibilityO[k]*=decay;
						if (gridPoints[i][j].boundary)
							if (maxBoundaryVisibilityO<gridPoints[i][j].visibilityO[k]) maxBoundaryVisibilityO=gridPoints[i][j].visibilityO[k];
					}
				}
				if (gridPoints[i][j].visibility>0) {
					gridPoints[i][j].visibility*=decay;
					if (gridPoints[i][j].visibility < 0.001) gridPoints[i][j].visibility=0;
					if (maxVisibility<gridPoints[i][j].visibility) maxVisibility=gridPoints[i][j].visibility;
					if (gridPoints[i][j].boundary)
						if (maxBoundaryVisibility<gridPoints[i][j].visibility) maxBoundaryVisibility=gridPoints[i][j].visibility;
				}
			}
		}
	}

	public void initGridStatus(Vector<Building>buildings, Vector<Building>obstacles, Vector<PVector>sitepoly) {
		//Solidity = new int[xSize][ySize]; 
	    //Walkobstruction = new int[xSize][ySize];
		for (int i = 0; i < gridPoints.length; i++) {
			for (int j = 0; j < gridPoints[i].length; j++) {
				gridPoints[i][j].openspace = true;
				gridPoints[i][j].permablocked = false;
				gridPoints[i][j].boundary = false;
			}
		}
	    int pnum = -1;
	    
	    //set obstructed by buildings
	    for (int x = 0; x < gridPoints.length; x++) {
			for (int y = 0; y < gridPoints[x].length; y++) {
				pnum = pointObstructed(buildings, sx + x*gridsize,sy + y*gridsize);  //there can be many on top of each other, check if there is one on the floor!
				if (pnum != -1) 
				{ 
					gridPoints[x][y].openspace = false;
				}
				else {
					pnum = pointObstructed(obstacles, sx + x*gridsize,sy + y*gridsize);  //there can be many on top of each other, check if there is one on the floor!
					if (pnum != -1) 
					{ 
						gridPoints[x][y].openspace = false;
					}
				}
				pnum =  pointInSite(sitepoly, sx + x*gridsize,sy + y*gridsize);
				if (pnum == -1) 
				{ 
					gridPoints[x][y].permablocked = true;
				}
			}
	    }
	    // set boundary
	    for (int x = 0; x < gridPoints.length; x++) {
			for (int y = 0; y < gridPoints[x].length; y++) {
				if (!gridPoints[x][y].openspace) {
					boolean b = false;
					for (int k = x-1; k < x+2; k++) {
						for (int kk = y-1; kk < y+2; kk++) {
							if (k==0&&kk==0) continue;
							if (k>0&&k<gridPoints.length) {
								if (kk>0&&kk<gridPoints[k].length) {
									if (gridPoints[k][kk].openspace==true) b = true;
								}
							}
						}
					}
					if (b==true) gridPoints[x][y].boundary = true;
					
				}
			}
		}
	    
	}
	
	private int pointInSite(Vector <PVector> sitepoly, float x, float y)
	{
		if (sitepoly!=null) {
			if (myMath.pointInPoly(x, y, sitepoly)) {
		    	return 0;
		    }
		}
		return -1;
	}

	int pointObstructed(Vector<Building> buildings, float x, float y) {
		if (buildings!=null) {
			for (int i = 0; i < buildings.size(); i++)
			{
			    Building p = buildings.elementAt(i);
			    if (p == null) continue;
			    if (p.footprint.vertices == null) continue;
			    if (p.footprint.vertices.size() == 0) continue;
			    if (p.footprint.vertices.elementAt(0).z > 1.5) continue;  // threshold for building considered to be on the ground
			    //if (p.InsertionPoint.z > 0.01) continue;
			    //test against bounding rectangle
			    if (x<p.footprint.minX || y<p.footprint.minY || x>p.footprint.maxX || y>p.footprint.maxY) continue;
			    
			    //if ( p.pointInside(x,y, p.vertices)) return i;
			    if (myMath.pointInPoly(x, y, p.footprint.vertices)) {
			    	return i;
			    }
			 }
		}
		return -1;
	}

	public int getGridcellX(float x) {
		return PApplet.round((x - sx) / gridsize);
	}
	public int getGridcellY(float y) {
		return PApplet.round((y - sy) / gridsize);
	}



}
