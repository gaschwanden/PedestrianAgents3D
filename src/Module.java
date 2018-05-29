import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;
import utility.DXFFace;
import utility.DXFHandler;
import utility.DXFPoly;
import utility.DXFVertex;
import utility.MyGL;
import utility.SimpleFootprint;


public class Module {
	PApplet p;
	PVector insertionPoint;
	public Vector<DXFPoly> polys;
	public Vector<DXFPoly> footprints;
	
	MyGL myGL;
	
	public Vector<SimpleFootprint> foot_untransformed;  // the real world footprint

	float rotation = 0;

	public Module(PApplet _p, DXFHandler _dxf) {
		// this method is for generating the generic module from dxf
		p=_p;
		myGL = new MyGL(p);
		//polys = _dxf.polys;  //todo: filter footprint
		polys = new Vector<DXFPoly>();
		footprints = new Vector<DXFPoly>();
		foot_untransformed = new Vector<SimpleFootprint> ();
		
		for (int i = 0; i < _dxf.polys.size(); i++) {
			
			// copy over the non footprint ones
			if (_dxf.polys.elementAt(i).layer.equals("FOOTPRINT"))
				footprints.addElement(_dxf.polys.elementAt(i));
			else 
				polys.addElement(_dxf.polys.elementAt(i));
		}
		insertionPoint = new PVector();
		centre();			//optional
		makeUntransformedFootprint();
	}
	
	public Module(Module m, PVector m_pos3D) {
		// this method is for copying a generic module from the library, to use in the scene
		p=m.p;
		myGL = new MyGL(p);
		polys = m.polys;
		footprints = m.footprints;
		foot_untransformed = new Vector<SimpleFootprint> ();
		insertionPoint = new PVector(m_pos3D.x, m_pos3D.y, m_pos3D.z);
		makeUntransformedFootprint();
	}

	public void draw()
	{
		p.stroke(255,0,0);
		p.strokeWeight(2);
		for (int i = 0; i < foot_untransformed.size(); i++) {
			SimpleFootprint fp = foot_untransformed.elementAt(i);
			for (int k = 0; k < fp.vertices.size(); k++) {
				PVector v1 = fp.vertices.elementAt(k);
				PVector v2 = fp.vertices.elementAt((k+1) % fp.vertices.size()) ;
				p.line((float)v1.x,(float)v1.y,(float)v1.z,(float)v2.x,(float)v2.y,(float)v2.z);
			}
		}
		p.strokeWeight(1);
		
		p.pushMatrix();
		p.translate(insertionPoint.x,  insertionPoint.y, insertionPoint.z);

		
		p.rotate(rotation);
		
		// footprint...............................................
				p.stroke(100);
				for (int i = 0; i < footprints.size(); i++) {
					DXFPoly pp = footprints.elementAt(i);
					for (int j = 0; j < pp.faces.size(); j++) {

						DXFFace f = pp.faces.elementAt(j);

						for (int k = 0; k < f.vertices.size(); k++) {
							DXFVertex v1 = f.vertices.elementAt(k);
							DXFVertex v2 = f.vertices.elementAt((k+1) % f.vertices.size()) ;
							if (f.visible.elementAt(k))
								p.line((float)v1.x,(float)v1.y,(float)v1.z,(float)v2.x,(float)v2.y,(float)v2.z);
						}
					}
				}
		
		// faces fill...............................................
			p.noStroke();
			p.fill(200);
			for (int i = 0; i < polys.size(); i++) {
				DXFPoly pp = polys.elementAt(i);
				
				for (int j = 0; j < pp.faces.size(); j++) {
	
					DXFFace f = pp.faces.elementAt(j);
	
					p.beginShape();
					for (int k = 0; k < f.vertices.size(); k++) {
						DXFVertex v = f.vertices.elementAt(k);
						p.vertex((float)v.x, (float)v.y, (float)v.z);
					}
					p.endShape(p.CLOSE);
				}
			}
		// faces outline...............................................
			p.stroke(100);
			for (int i = 0; i < polys.size(); i++) {
				DXFPoly pp = polys.elementAt(i);
				for (int j = 0; j < pp.faces.size(); j++) {
	
					DXFFace f = pp.faces.elementAt(j);
	
					for (int k = 0; k < f.vertices.size(); k++) {
						DXFVertex v1 = f.vertices.elementAt(k);
						DXFVertex v2 = f.vertices.elementAt((k+1) % f.vertices.size()) ;
						if (f.visible.elementAt(k))
							p.line((float)v1.x,(float)v1.y,(float)v1.z,(float)v2.x,(float)v2.y,(float)v2.z);
					}
				}
			}
		
		p.popMatrix();
	}
	
	public void rotate(Pointer P)
	{
		// 1 get the current and the previous rotation angle according to the initial pointer down point
	    PVector dir = new PVector(P.m_pos3D.x, P.m_pos3D.y);
	    PVector pdir = new PVector(P.m_ppos3D.x, P.m_ppos3D.y);
	    dir.x = dir.x-P.m_fpos3D.x; dir.y = dir.y-P.m_fpos3D.y;
	    pdir.x = pdir.x-P.m_fpos3D.x; pdir.y = pdir.y-P.m_fpos3D.y;
	    
	    if (dir.mag() ==0) return;
	    if (pdir.mag() ==0) return;
	    
	    dir.normalize(); pdir.normalize();
	    
	    float angle = -p.atan(dir.x/dir.y) + p.PI/2;
	    if(dir.y<0)angle =p.PI+p.atan(dir.x/-dir.y)+ p.PI/2;
	    float pangle = -p.atan(pdir.x/pdir.y) + p.PI/2;
	    if(pdir.y<0)pangle =p.PI+p.atan(pdir.x/-pdir.y)+ p.PI/2;
	    
	    //handle break of angle value around PI*2 .. 0, which is the positive x direction
	    float dangle = angle-pangle;
	    if (dangle > p.PI) { dangle -= p.PI*2;  }
	    else if (dangle < -p.PI) { dangle = p.PI*2 + dangle;  }
	    
	    rotation += dangle;
	    //p.println(rotation);
	    
	    float snapTol = 0.1f;
	    float rot = rotation % p.TWO_PI;
	    if (p.abs(rot) < snapTol) rotation = 0;
	    if (p.abs(rot-p.PI) < snapTol) rotation = p.PI;
	    if (p.abs(rot-p.PI/2.0f) < snapTol) rotation = p.PI/2.0f;
	    if (p.abs(rot-p.PI/2.0f*3.0f) < snapTol) rotation = p.PI/2.0f*3.0f;
	    
	    makeUntransformedFootprint();
	}
	
	public void makeUntransformedFootprint()
	{
		foot_untransformed = new Vector<SimpleFootprint>();
		for (int i = 0; i < footprints.size(); i++) {
			DXFPoly pp = footprints.elementAt(i);
			
			for (int j = 0; j < pp.faces.size(); j++) {

				DXFFace f = pp.faces.elementAt(j);
				foot_untransformed.addElement(new SimpleFootprint(p));

				for (int k = 0; k < f.vertices.size(); k++) {
					DXFVertex v1 = f.vertices.elementAt(k);

					//get the direction to the vertex from the rotation point
				    PVector a = new PVector((float)v1.x, (float)v1.y, (float)v1.z);
				    PVector vdir = new PVector();
				    vdir.x = a.x; vdir.y = a.y;
				    vdir.x = vdir.x-0; vdir.y = vdir.y-0;  // rotate around origin 0,0
				    if (vdir.mag()==0) continue;
				    //keep the length of the vector to the vertex
				    float len = vdir.mag();
				    vdir.normalize();
				    float vangle = -p.atan(vdir.x/vdir.y) + p.PI/2.0f;
				    if(vdir.y<0)vangle =p.PI+p.atan(vdir.x/-vdir.y)+ p.PI/2.0f;
				      
				    //add the delta angle to the vertex angle
				      vangle += rotation;
				      
				    //calculate the new coordinates for the vertex
				      float xx = p.cos(vangle); float  yy = p.sin(vangle);
				      xx *= len; yy *= len;
				      xx+=0; yy+=0;  // origin

				      foot_untransformed.lastElement().vertices.addElement(new PVector(xx+ insertionPoint.x,yy +insertionPoint.y,0+insertionPoint.z));
				      foot_untransformed.lastElement().verticesS.addElement(new PVector());
				}
			}
		}
	}

	private void centre() {   // centre the drawing aroud the middle 
		double minx = 99999999.9f;
		double miny = 99999999.9f;
		double maxx = -99999999.9f;
		double maxy = -99999999.9f;
		
		for (int i = 0; i < polys.size(); i++) {
			DXFPoly pp = polys.elementAt(i);
			for (int j = 0; j < pp.vertices.size(); j++) {
				DXFVertex v = pp.vertices.elementAt(j);
				if (v.x < minx) minx = v.x;
				if (v.y < miny) miny = v.y;
				if (v.x > maxx) maxx = v.x;
				if (v.y > maxy) maxy = v.y;
			}
		}
		for (int i = 0; i < footprints.size(); i++) {
			DXFPoly pp = footprints.elementAt(i);
			for (int j = 0; j < pp.vertices.size(); j++) {
				DXFVertex v = pp.vertices.elementAt(j);
				if (v.x < minx) minx = v.x;
				if (v.y < miny) miny = v.y;
				if (v.x > maxx) maxx = v.x;
				if (v.y > maxy) maxy = v.y;
			}
		}
		//p.println(minx+" "+maxx);
		//p.println(miny+" "+maxy);
		
		double dx = (maxx-minx) / 2.0f;
		double dy = (maxy-miny) / 2.0f;
		double movex = minx+dx;
		double movey = miny+dy;
		
		for (int i = 0; i < polys.size(); i++) {
			DXFPoly p = polys.elementAt(i);
			for (int j = 0; j < p.vertices.size(); j++) {
				DXFVertex v = p.vertices.elementAt(j);
				v.x -= movex;
				v.y -= movey;
				
			}
		}
		for (int i = 0; i < footprints.size(); i++) {
			DXFPoly p = footprints.elementAt(i);
			for (int j = 0; j < p.vertices.size(); j++) {
				DXFVertex v = p.vertices.elementAt(j);
				v.x -= movex;
				v.y -= movey;
				
			}
		}
	}

	public void project(PGraphicsOpenGL g3d, int winW, int winH) {
		// for now we are just projecting the real world footprint
		
		for (int k = 0; k < foot_untransformed.size(); k++) {
			SimpleFootprint footprint = foot_untransformed.elementAt(k);
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

	public void snap(Vector<PVector> snappts) {
		float snapdist = 5000;
		for (int i = 0; i < snappts.size(); i++) {
			p.println(p.abs(snappts.elementAt(i).x - insertionPoint.x) + " "+p.abs(snappts.elementAt(i).y - insertionPoint.y));
			if (p.abs(snappts.elementAt(i).x - insertionPoint.x) < snapdist &&  p.abs(snappts.elementAt(i).y - insertionPoint.y) < snapdist) {
				insertionPoint.x = snappts.elementAt(i).x;
				insertionPoint.y = snappts.elementAt(i).y;
				makeUntransformedFootprint();
				return;
			}
		}
		
	}
}
