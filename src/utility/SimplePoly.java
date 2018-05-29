package utility;

import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

public class SimplePoly {
	public Vector <PVector> vertices;
	
	public SimplePoly()
	{
		vertices = new Vector<PVector>();
	}
	
	public void draw(PApplet p)
	{
		p.stroke(255);
		p.noFill();
		p.beginShape();
		for (PVector v : vertices) {
			p.vertex(v.x,v.y,v.z);
		}
		p.endShape();
		p.strokeWeight(4);
		for (PVector v : vertices) {
			p.point(v.x,v.y,v.z);
		}
		p.strokeWeight(1);
	}
	
	public void addVertex(float x, float y, float z)
	{
		PVector v = new PVector(x,y,z);
		vertices.addElement(v);
	}

}
