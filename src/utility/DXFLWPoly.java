package utility;

import java.util.Vector;


public class DXFLWPoly {
	public String layer;
	public Vector<DXFVertex> vertices;
	
	public DXFLWPoly ()
	{
		vertices = new Vector<DXFVertex>();
	}
	public void addVertex()
	{
		vertices.addElement(new DXFVertex());
	}
	
	public DXFLWPoly scale(float factor) {
		for (int i = 0; i < vertices.size(); i ++)
		{
			vertices.elementAt(i).x *= factor;
			vertices.elementAt(i).y *= factor;
			vertices.elementAt(i).z *= factor;
		}
		return this;
	}
}
