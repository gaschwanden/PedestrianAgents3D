package utility;

import java.util.Vector;

import processing.core.PVector;

public class DXFFace {
	public Vector<DXFVertex> vertices;
	public Vector<Boolean> visible;
	
	public DXFFace()
	{
		vertices = new Vector<DXFVertex>();
		visible  = new Vector<Boolean>();
	}
}
