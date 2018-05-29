import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

import utility.DXFLine;


public class Site {
	Vector<PVector> insertionpoints;
	//Vector<DXFLine> lines;
	
	Vector <PVector> poly;
	
	PApplet p;
	
	public Site(PApplet _p) {
		p=_p;
		poly = new Vector<PVector>();
		//lines = new Vector<DXFLine>();
		insertionpoints = new Vector<PVector>();
	}
	
	public void draw(int analysis_mode)
	{
		p.stroke(50,0,0);
		p.noFill();
		p.beginShape();
		for (int i = 0; i < poly.size(); i++) {
			p.vertex(poly.elementAt(i).x, poly.elementAt(i).y, 0);
		}
		p.endShape(p.CLOSE);
		
		
	}

}
