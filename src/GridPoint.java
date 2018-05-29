import processing.core.PApplet;


public class GridPoint {
	Grid grid;
	float dist[];
	boolean openspace = true;
	boolean permablocked = false;
	
	public float occupancy;
	public float visibility;
	public float visibilityO[];
	public boolean boundary;

	public GridPoint(Grid _grid, int maxNumOd) {
		grid=_grid;
		dist = new float[maxNumOd];
		visibilityO = new float[maxNumOd];
	}
	
	public void drawTest(PApplet p, int i, int j)
	{
		p.rectMode(PApplet.CENTER);
		if (walkable() && dist[0]>0){
			p.fill(dist[0]*10);
			p.noStroke();
			p.rect(grid.sx+i*grid.gridsize, grid.sy+j*grid.gridsize,grid.gridsize, grid.gridsize);
		}
	}

	public void drawOccupation(PApplet p, int i, int j) {
		p.rectMode(PApplet.CENTER);
		/*if (filled) {
			int d = (int) dist[0];
			if (d%10<9) p.stroke(255); else p.stroke(255,0,0);
		
			p.point(sx+i*gridsize, sy+j*gridsize);
		}*/
		if (walkable() && occupancy>0) {
			//int d = (int) gridPoints[i][j].dist[0];
			//if (d%10<9) p.stroke(255); else p.stroke(255,0,0);
			//p.stroke(255-gridPoints[i][j].dist[0]*5);
			
			float val = PApplet.map(occupancy, 0, grid.maxOccupation,0, 255);
//			p.fill(val*3,0,0); // // 
			p.fill(255,255-(val*4),255-(val*4)); 
			
			
			//p.fill(val,90-PApplet.abs(90-val),2-PApplet.abs(20-val));//125-PApplet.abs(100-val));
			
			//p.fill(val,80-val/4,150-val/2);
			/*if (val>150) {
				p.fill(val,80-val/2,150-val);
			}
			else {
				p.fill(val,0,val-(150-val));
			}*/
			
			p.noStroke();
			p.rect(grid.sx+i*grid.gridsize, grid.sy+j*grid.gridsize,grid.gridsize, grid.gridsize);
		
			/*
			p.stroke(val,80-val/4,150-val/2);
			p.strokeWeight(val/40+1);
			p.point(grid.sx+i*grid.gridsize, grid.sy+j*grid.gridsize);
			p.strokeWeight(1);
			*/
		}
		 
		/*p.stroke(255,0,0);
		if (!filled) p.fill(100);
		else p.noFill();
		p.rect(sx+i*gridsize, sy+j*gridsize,gridsize, gridsize);
		p.point(sx+i*gridsize, sy+j*gridsize);*/
		
	}
	
	public boolean walkable()
	{
		//return openspace && !permablocked;
		if (!openspace) return false;
		if (permablocked) return false;
		return true;
	}

	public void drawVisibility(PApplet p, int i, int j) {
		p.rectMode(PApplet.CENTER);
		if (visibility>0 /*&& boundary*/) {
			
			//float val = PApplet.map(visibility, 0, grid.maxVisibility,0, 255);
			float val = PApplet.map(visibility, 0, grid.maxBoundaryVisibility,0, 255);
//			p.fill(val,0,0);
			p.fill(255-(val*4),255-(val*4),255); 
			p.noStroke();
			p.rect(grid.sx+i*grid.gridsize, grid.sy+j*grid.gridsize,grid.gridsize, grid.gridsize);
			
		}
		//if (boundary) {
			//averageVisibility(i,j);
			//p.stroke(200);
			//p.fill(100);
			//p.rect(sx+i*gridsize, sy+j*gridsize,gridsize, gridsize);
		//}
		
	}


}
