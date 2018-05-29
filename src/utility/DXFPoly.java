package utility;

import java.util.Vector;

import processing.core.PVector;

public class DXFPoly {
	public String layer;
	public Vector<DXFVertex> vertices;
	public Vector<DXFFace> faces;
	
	
	
	public DXFPoly ()
	{
		vertices = new Vector<DXFVertex>();
		faces = new Vector<DXFFace>();
	}
	public void addVertex()
	{
		vertices.addElement(new DXFVertex());
	}
	public void addFace()
	{
		faces.addElement(new DXFFace());
	}
	public void addFaceFromVertexList() {
		// fix
		
		DXFFace f = new DXFFace();
		for (int i = 0; i < vertices.size(); i++) {
			f.vertices.addElement(vertices.elementAt(i));
			f.visible.addElement(true);
		}
		faces.addElement(f);
	}
	public void scale(float scaler) {
		for (DXFVertex v : vertices) {
			v.x*=scaler;
			v.y*=scaler;
			v.z*=scaler;
		}
		
	}
}
