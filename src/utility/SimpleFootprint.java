package utility;

import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

// a class for a simple untransformed footprint for our module class

public class SimpleFootprint {
	public Vector<PVector> vertices;
	public Vector <PVector> verticesS;
	
	float minX, minY, maxX, maxY;                      //the bounding rectangle
	float pminX, pminY, pmaxX, pmaxY;                  //the previous bounding rectangle
	float minXS, minYS, maxXS, maxYS;                  //the bounding rectangle on the screen
	
	MyMath myMath;
	PApplet p;
	
	public SimpleFootprint(PApplet _p)
	{
		p=_p;
		vertices = new Vector<PVector>();
		verticesS = new Vector<PVector>();
		myMath = new MyMath(p);
	}

	public boolean hitTestS(int x, int y) {
		// point in footprint polygon?
				if (verticesS==null)    return false;
				
				//check against bounding rectangle
				if (x < (minXS)) 		return false;
				if (y < (minYS)) 		return false;
				if (x > (maxXS)) 		return false;
				if (y > (maxYS)) 		return false;
				
				return myMath.pointInPoly(x, y, verticesS);
		
	}
	public void setBoundingRectangle() {
		minX=99999999999.9f; minY=99999999999.9f; maxX=-99999999999.9f; maxY=-99999999999.9f;
	    for (int i=0; i<vertices.size(); i++)
	    {
	      PVector v = vertices.elementAt(i);
	      if (minX > v.x) minX = v.x;
	      if (minY > v.y) minY = v.y;
	      if (maxX < v.x) maxX = v.x;
	      if (maxY < v.y) maxY = v.y;
	    }
		
	}
	public void setBoundingRectangleS() {
		minXS=99999999999.9f; minYS=99999999999.9f; maxXS=-99999999999.9f; maxYS=-99999999999.9f;
	    for (int i=0; i<verticesS.size(); i++)
	    {
	      PVector v = verticesS.elementAt(i);
	      if (minXS > v.x) minXS = v.x;
	      if (minYS > v.y) minYS = v.y;
	      if (maxXS < v.x) maxXS = v.x;
	      if (maxYS < v.y) maxYS = v.y;
	    }
	}

}
