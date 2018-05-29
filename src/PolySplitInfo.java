import java.util.Vector;

import processing.core.PVector;


public class PolySplitInfo
{
	  Building  poly;
	  Vector<PVector> intersections;     //store the intersection points for polygon subdivision
	  int[] vertices;                          //vertex indices between which to do the split
	  PolySplitInfo()
	  {
	    vertices = new int[4];          //to store the index of the vertices that are intersected between
	    intersections = new Vector<PVector>();   //to store the intersection points
	    poly = null;
	  }
	  }