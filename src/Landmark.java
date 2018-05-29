import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import utility.DXFFace;
import utility.DXFLWPoly;
import utility.DXFLine;
import utility.DXFMesh;
import utility.DXFPoly;


public class Landmark {
	PApplet p;
	Scene scene;
	public Vector<DXFLine> 		lines;
	public Vector<DXFPoly> 		polys;
	public Vector<DXFLWPoly> 	lwpolys;
	public Vector<DXFMesh> 		meshes;
	public Vector<Footprint> 	footprints;
	
	public Landmark(PApplet _p, Scene _scene) {
		p = _p;
		scene = _scene;
		
		lines = new Vector<DXFLine> ();
		polys = new  Vector<DXFPoly> ();
		lwpolys = new Vector<DXFLWPoly> ();
		meshes = new Vector<DXFMesh>();
		footprints = new Vector<Footprint>();
	}

	public void draw(int analysis_mode) {
		//p.println(polys.size());
		p.fill(80);
		p.noStroke();
		
		p.beginShape(p.TRIANGLES);
		for (int i = 0; i < polys.size(); i++) {
			DXFPoly poly = polys.elementAt(i);
			for (int k = 0; k < poly.faces.size(); k++) {
				DXFFace face = poly.faces.elementAt(k);
				//p.println(face.vertices.size());
				if (face.vertices.size()==3) {
					//p.line(0, 0, 0, ( float)face.vertices.elementAt(0).x, (float)face.vertices.elementAt(0).y, (float)face.vertices.elementAt(0).z);
					
					p.vertex((float)face.vertices.elementAt(0).x, (float)face.vertices.elementAt(0).y, (float)face.vertices.elementAt(0).z);
					p.vertex((float)face.vertices.elementAt(1).x, (float)face.vertices.elementAt(1).y, (float)face.vertices.elementAt(1).z);
					p.vertex((float)face.vertices.elementAt(2).x, (float)face.vertices.elementAt(2).y, (float)face.vertices.elementAt(2).z);
					
				}
			}
		}
		p.endShape();
		
		p.stroke(120);
		//p.strokeWeight(2);
		p.beginShape(p.LINES);
		for (int i = 0; i < lines.size(); i++) {
			p.vertex(lines.elementAt(i).x1, lines.elementAt(i).y1, lines.elementAt(i).z1);
			p.vertex(lines.elementAt(i).x2, lines.elementAt(i).y2, lines.elementAt(i).z2);
		}
		p.endShape();
		//p.strokeWeight(1);
		
	}

	public void move(float xoffs, float yoffs, float zoffs) {
		for (int i = 0; i < lines.size(); i++) {
			lines.elementAt(i).x1 += xoffs;
			lines.elementAt(i).y1 += yoffs;
			lines.elementAt(i).z1 += zoffs;
			lines.elementAt(i).x2 += xoffs;
			lines.elementAt(i).y2 += yoffs;
			lines.elementAt(i).z2 += zoffs;
		}
		for (int i = 0; i < polys.size(); i++) {
			for (int k = 0; k < polys.elementAt(i).vertices.size(); k++) {
				polys.elementAt(i).vertices.elementAt(k).x += xoffs;
				polys.elementAt(i).vertices.elementAt(k).y += yoffs;
				polys.elementAt(i).vertices.elementAt(k).z += zoffs;
			}
		}
		for (int i = 0; i < lwpolys.size(); i++) {
			for (int k = 0; k < lwpolys.elementAt(i).vertices.size(); k++) {
				lwpolys.elementAt(i).vertices.elementAt(k).x += xoffs;
				lwpolys.elementAt(i).vertices.elementAt(k).y += yoffs;
				lwpolys.elementAt(i).vertices.elementAt(k).z += zoffs;
			}
		}
		for (int i = 0; i < meshes.size(); i++) {
			for (int k = 0; k < meshes.elementAt(i).vertices.size(); k++) {
				meshes.elementAt(i).vertices.elementAt(k).x += xoffs;
				meshes.elementAt(i).vertices.elementAt(k).y += yoffs;
				meshes.elementAt(i).vertices.elementAt(k).z += zoffs;
			}
		}
		
		for (int k = 0; k < footprints.size(); k++) {
			Footprint footprint = footprints.elementAt(k);
			for (int i = 0; i < footprint.vertices.size(); i++) {
				footprint.vertices.elementAt(i).add(xoffs, yoffs, zoffs);
				if (i >= footprint.segpts.length) continue; 
				for (int j = 0; j < footprint.segpts[i].size(); j++) {
					PVector pt = (PVector)footprint.segpts[i].elementAt(j);
					pt.add(xoffs, yoffs, zoffs);
				}
			}
			footprint.setBoundingRectangle();
		}
	}

	public void setPolys(Vector<DXFPoly> pgs) {
		polys = pgs;
		
	}

}
