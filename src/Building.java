import java.util.Collections;

import processing.core.PApplet;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.MyGL;
import utility.MyMath;


public class Building {
	Footprint footprint;
	PApplet p;
	float height = 15;
	Scene scene;
	int num_floors;
	
	String type = "building";
	
	MyGL myGL;
	public boolean vertexdragged = false;;
	
	int outline_col = 150;
	String dxfLayer;
	
	public Building(PApplet _p, Scene _scene, int _num_floors, String _type, String _layer)
	{
		p=_p;
		scene=_scene;
		type = _type;
		num_floors=_num_floors;
		height = num_floors*3;
		footprint = new Footprint(p);
		myGL = new MyGL(p);
		dxfLayer = _layer;
	}
	
	public Building(Building B)
	{
		p=B.p;
		scene=B.scene;
		type = B.type;
		num_floors=B.num_floors;
		height = B.height;
		footprint = new Footprint(p);
		myGL = new MyGL(p);
		dxfLayer = B.dxfLayer;
	}
	
	

	public void draw(int display_mode) {
		if (	   display_mode == scene.display_pathoverlap 
				|| display_mode == scene.display_noAnalysis 
				|| scene.grid.maxBoundaryVisibility==0) {
			if (!vertexdragged) 
				drawSimple();
			else 
				drawOutline(outline_col,outline_col,outline_col);
			return;
		}
		else if (   display_mode == scene.display_traces
				 || display_mode == scene.display_tracesO) {
			if (!vertexdragged) 
				//drawSimpleFill();
				drawSimple();
			else 
				drawOutline(outline_col,outline_col,outline_col);
			return;
		}
		else if (display_mode==scene.display_facadevisibility ) {
			if (!vertexdragged) 
				drawFacadeVisibility();
			else 
				drawOutline(outline_col,outline_col,outline_col);
			return;
		}
		else if (display_mode==scene.display_facadevisibilityO ) {
			if (!vertexdragged) 
				drawFacadeVisibilityO();
			else 
				drawOutline(outline_col,outline_col,outline_col);
			return;
		}
	}
	
	
	public void drawAsObstacle(int display_mode) {
		p.pushMatrix();
		p.translate(0, 0,-0.1f);
		//p.println(dxfLayer);
		if (dxfLayer.equals("OBSTACLES_HIGH")) {
			drawOutline(outline_col-50,outline_col-50,outline_col-50);
		}
		else if (dxfLayer.equals("OBSTACLES_LOW")) {
			drawOutline(outline_col-50,outline_col-50,outline_col-50);
		}
		else if (dxfLayer.equals("STREETS")) {
			drawOutline(outline_col,outline_col,outline_col);
		}
		else {
			int col = p.color(50);
			if (dxfLayer.equals("WATERBODY")) {
				col = p.color(200,230,255);
			}
			else if (dxfLayer.equals("PARK")) {
				//col = p.color(50,70,0);
				col = p.color(50);
			}
			footprint.drawFill(col);
		}
		p.popMatrix();
	}
	
	public void draw2D(int displayMode)
	{
		if (scene.interaction_mode != Scene.mode_BD_edit && scene.interaction_mode != Scene.mode_OB_edit) return;
		if (scene.interaction_mode == Scene.mode_BD_edit && !type.equals("building")) return;
		if (scene.interaction_mode == Scene.mode_OB_edit && !type.equals("obstacle")) return;
		p.stroke(outline_col);
		int l=2;
		PVector pos;
		for (int i=0; i<footprint.verticesS.size(); i++)
	    {
			pos = footprint.verticesS.elementAt(i);
			//pos = new PVector(p.random(p.width),p.random(p.height));
			if (pos.z>=1) continue;  // not valid
			//p.line(500, 30, pos.x, pos.y);
			p.line((int)pos.x-l, (int)pos.y,  (int)pos.x+l, (int)pos.y);
			p.line((int)pos.x,   (int)pos.y-l,(int)pos.x,   (int)pos.y+l);
			
	    }
	}
	
	private void drawSimple() {
		footprint.draw();
		for (int i=0; i<footprint.vertices.size(); i++)
	    {
			//p.fill(100,100);
			p.fill(255,100);
			//p.noFill();
			
			//p.stroke(100);
			p.stroke(outline_col);
			//p.noStroke();
			p.beginShape();
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z );
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z );
			p.endShape(p.CLOSE);
		}
		drawRoof();
	}
	
	private void drawSimpleFill() {
		footprint.draw();
		for (int i=0; i<footprint.vertices.size(); i++)
	    {
			p.fill(150,100);
			p.noStroke();
			p.beginShape();
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z );
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z );
			p.endShape(p.CLOSE);
		}
		drawRoof();
	}
	

	private void drawOutline(int r, int g, int b) {
		//footprint.draw();
		for (int i=0; i<footprint.vertices.size(); i++)
	    {
			p.noFill();
			
			//p.stroke(outline_col);
			p.stroke(r,g,b);
			//p.noStroke();
			p.beginShape();
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z );
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z );
			p.endShape(p.CLOSE);
		}
	}
	
	private void drawFacadeVisibility()
	{
		PixRef pixel;
		int px,py;
		// sides
		p.beginShape();
		for (int i=0; i<footprint.vertices.size(); i++)
	    {
			p.noFill();
			if (scene.grid.maxBoundaryVisibility==0) {
				p.stroke(outline_col);
				p.beginShape();
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z );
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z );
				p.endShape(p.CLOSE);
			}
			
			//facade segments
			if (i >= footprint.segpts.length) continue; 
			p.noStroke();
			
			p.fill(255,90);
			if (i >= footprint.segs_pixrefs.length) continue;
			
			for (int j = 0; j < footprint.segpts[i].size()-1; j++) {
				PVector pt1 = (PVector)footprint.segpts[i].elementAt(j);
				PVector pt2 = (PVector)footprint.segpts[i].elementAt(j+1);
				
				if (scene.grid.maxBoundaryVisibility>0) {
					
					if (footprint.segs_pixrefs[i].size() < j) continue;
					pixel = (PixRef)footprint.segs_pixrefs[i].elementAt(j);
					px = (int) pixel.pixx;
					py = (int) pixel.pixy;
					// security
					if (px<0||px>=scene.grid.gridPoints.length) continue;
					if (py<0||py>=scene.grid.gridPoints[px].length) continue;
					
					if (scene.grid.gridPoints[px][py].visibility == 0) {
						//p.fill(0,30,20);
						p.fill(255,255-20,255-30);
					}
					else {
						// no average
						//float val = PApplet.map(scene.grid.gridPoints[px][py].visibility, 0, scene.grid.maxBoundaryVisibility,0, 255);
						//p.fill(val,80-val/4,150-val/2, val+50);
						
						// average
						float val = scene.grid.gridPoints[px][py].visibility;
						float val2 = val;
						float num = 1;
						for (int k = px-1; k < px+2; k++) {
							if (k>=0&& k<scene.grid.gridPoints.length) {
								for (int kk = py-1; kk < py+2; kk++) {
									if (kk>=0&& kk<scene.grid.gridPoints[k].length) {
										if (scene.grid.gridPoints[k][kk].visibility > val) {  // only upwards
											val2+=scene.grid.gridPoints[k][kk].visibility;
											num+=1;
										}
									}
								}
							}
						}
						val2 /= num;
						val = PApplet.map (val2, 0, scene.grid.maxBoundaryVisibility,0, 255);
						//p.fill(val,80-val/4,150-val/2, val+50); // // 
						p.fill(val,80-val/4,150-val/2, (val+50)*2);
						//
						
					}	
				}
				
				p.beginShape();
					p.vertex(pt1.x,   pt1.y,   footprint.vertices.elementAt(i).z );
					p.vertex(pt1.x,   pt1.y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(pt2.x,   pt2.y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(pt2.x,   pt2.y,   footprint.vertices.elementAt(i).z );
				p.endShape(p.CLOSE);
			}
	    }
		//drawRoof();
	}
	
	private void drawFacadeVisibilityO()
	{
		PixRef pixel;
		int px,py;
		// sides
		p.beginShape();
		for (int i=0; i<footprint.vertices.size(); i++)
	    {
			p.noFill();
			if (scene.grid.maxBoundaryVisibility==0) {
				p.stroke(outline_col);
				p.beginShape();
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z );
					p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z + height);
					p.vertex(footprint.vertices.elementAt((i+1)%footprint.vertices.size()).x,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).y,   footprint.vertices.elementAt((i+1)%footprint.vertices.size()).z );
				p.endShape(p.CLOSE);
			}
			
			//facade segments
			if (i >= footprint.segpts.length) continue; 
			p.noStroke();
			
			p.fill(150);
			if (i >= footprint.segs_pixrefs.length) continue;
			
			for (int j = 0; j < footprint.segpts[i].size()-1; j++) {
				PVector pt1 = (PVector)footprint.segpts[i].elementAt(j);
				PVector pt2 = (PVector)footprint.segpts[i].elementAt(j+1);
				
				if (scene.grid.maxBoundaryVisibilityO>0) {
					
					if (footprint.segs_pixrefs[i].size() < j) continue;
					pixel = (PixRef)footprint.segs_pixrefs[i].elementAt(j);
					px = (int) pixel.pixx;
					py = (int) pixel.pixy;
					// security
					if (px<0||px>=scene.grid.gridPoints.length) continue;
					if (py<0||py>=scene.grid.gridPoints[px].length) continue;
					
					if (scene.grid.gridPoints[px][py].visibilityO[0] == 0
							&& scene.grid.gridPoints[px][py].visibilityO[1] == 0
							&& scene.grid.gridPoints[px][py].visibilityO[2] == 0) {
						//p.fill(0,30,20);
						p.fill(230);
					}
					else {
						
						 float val = PApplet.map(scene.grid.gridPoints[px][py].visibilityO[0], 0, scene.grid.maxBoundaryVisibilityO,20, 255);
						 float valx = PApplet.map(scene.grid.gridPoints[px][py].visibilityO[1], 0, scene.grid.maxBoundaryVisibilityO,20, 255);
						 float valxx = PApplet.map(scene.grid.gridPoints[px][py].visibilityO[2], 0, scene.grid.maxBoundaryVisibilityO,20, 255);
						 p.fill(255-valx-valxx,255-val -valxx,255- val/*, (val+valx+valxx)/3.0f+50*/);
					}	
				}
				
				p.beginShape();
					p.vertex(pt1.x,   pt1.y,   footprint.vertices.elementAt(i).z );
					p.vertex(pt1.x,   pt1.y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(pt2.x,   pt2.y,   footprint.vertices.elementAt(i).z + height);
					p.vertex(pt2.x,   pt2.y,   footprint.vertices.elementAt(i).z );
				p.endShape(p.CLOSE);
			}
	    }
		//drawRoof();
	}
	
	
	
	private void drawRoof() {
		p.noStroke();
		p.fill(50,100);
		p.beginShape();
		for (int i=0; i<footprint.vertices.size(); i++) {
				p.vertex(footprint.vertices.elementAt(i).x,   footprint.vertices.elementAt(i).y,   footprint.vertices.elementAt(i).z + height);
		}
		p.endShape(p.CLOSE);
		
	}
	
	void fixPolygonVertexOrder()  
	  {
	    //we want the building footprints to be drawn CW
	    int cw = MyMath.clockWise(footprint.vertices);
	    if (cw == -1)  //ccw...need to swap vertices
	    {
	      //flipped = true;
	      Collections.reverse(footprint.vertices);
	      //p.println("flip");
	    }
	  }

	public void move(float xoffs, float yoffs, float zoffs) {
		for (int i = 0; i < footprint.vertices.size(); i++) {
			//p.println(footprint.vertices.elementAt(i));
			footprint.vertices.elementAt(i).add(xoffs, yoffs, zoffs);
			//p.println(footprint.vertices.elementAt(i));
			if (i >= footprint.segpts.length) continue; 
			for (int j = 0; j < footprint.segpts[i].size(); j++) {
				PVector pt = (PVector)footprint.segpts[i].elementAt(j);
				//p.println(pt);
				pt.add(xoffs, yoffs, zoffs);
				//p.println(pt);
			}
		}
		footprint.setBoundingRectangle();
	}

	public void project(PGraphicsOpenGL g3d, int winW, int winH) {
		if (footprint.verticesS==null) 								return;
		if (footprint.verticesS.size()<footprint.vertices.size()) 	return;
		float [] coords = new float[4];
		PVector pos;
		for (int i = 0; i < footprint.vertices.size(); i++) {
			pos = footprint.vertices.elementAt(i);
		    int res = myGL.projectScreenCoords(g3d, pos.x, pos.y, pos.z, coords, winW, winH);
		    footprint.verticesS.elementAt(i).x = (int)coords[0];
		    footprint.verticesS.elementAt(i).y = (int)coords[1]; 
		    footprint.verticesS.elementAt(i).z = (int)coords[2]; //note! if coords[2] >= 1 the result is not valid
		}
		footprint.setBoundingRectangleS();
		
	}
	
}
