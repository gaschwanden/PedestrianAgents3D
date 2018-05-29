package utility;
import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

public class MyMath {
	PApplet p;
	public MyMath(PApplet _p)
	{
		p=_p;
	}
	
	public float dist(float x1, float y1, float z1, float x2, float y2, float z2) {
		float a = x2-x1;
		float b = y2-y1;
		float c = z2-z1;
		return p.sqrt(a*a+b*b+c*c);
	}

	public boolean pointInPoly(float x, float y, Vector<PVector> pg) {
		boolean  oddNodes=false;
	    PVector a,b;
	    
	    int j = pg.size()-1;
	    
	    for (int i = 0; i < pg.size(); i++) {
	      b = pg.elementAt(j);
	      a = pg.elementAt(i);
	      if ((a.y < y && b.y >= y) || (b.y < y && a.y >= y)) {
	        if (a.x+ (y-a.y) / (b.y -a.y) * (b.x-a.x) < x) {
	          oddNodes=!oddNodes; 
	        }
	      }
	      j=i; 
	    }
	    return oddNodes;
	}
	
	public static int clockWise(Vector<PVector> vertices) {
		float c = area(vertices);
	    if (c > 0) return 1;     //ccw
	    else if (c < 0) return -1; //cw
	    return 0;
	}
	
	public static float area(Vector <PVector> pts)
	  {
	    PVector a,b;
	    float r = 0;
	    for (int i = 0; i < pts.size(); i++) 
	    {
	      a = (PVector)pts.elementAt(i);
	      if (i < pts.size()-1) b = (PVector)pts.elementAt(i+1);
	      else b = (PVector)pts.elementAt(0);
	      
	      r += (a.x*b.y - a.y*b.x);
	    }
	    r/=2;
	    return r;
	  }
	
	
	public static void splitPolygon(Vector<PVector> verts, Vector<PVector>  verts1, Vector<PVector>  verts2, Vector<PVector> intersections, int[] vertices)
	{
	  PVector inter1 = intersections.elementAt(0);
	  PVector inter2 = intersections.elementAt(1);

	    
	  //the first polygon 
	  for (int j = 0; j < vertices[1]; j++) {
	    PVector v = verts.elementAt(j);
	    verts1.addElement(new PVector(v.x,v.y)); 
	  }
	  verts1.addElement(new PVector(inter1.x,inter1.y));  
	  verts1.addElement(new PVector(inter2.x,inter2.y));  
	  for (int j = vertices[3]; j < verts.size(); j++) {
	    PVector v = verts.elementAt(j);
	    verts1.addElement(new PVector(v.x,v.y)); 
	  }
	    
	  //the second polygon 
	  verts2.addElement(new PVector(inter1.x,inter1.y));
	  for (int j = vertices[1]; j < vertices[3]; j++) {
	    PVector v = verts.elementAt(j);
	    verts2.addElement(new PVector(v.x,v.y));  
	  }
	  verts2.addElement(new PVector(inter2.x,inter2.y));
	}
	
	public static void LinePolyIntersectons(Vector<PVector> vertexList, float fx, float fy, float x, float y, Vector<PVector> intersections, int [] vertices)
	{
	  PVector a,b;
	  for (int i = 0; i < vertexList.size(); i++) {
	    a = vertexList.elementAt(i);
	    if (i < vertexList.size()-1) b = (PVector)vertexList.elementAt(i+1);
	    else b = (PVector)vertexList.elementAt(0);
	    PVector inter = lineSegmentIntersection(fx, fy, x, y, a.x, a.y, b.x, b.y);
	 
	    if (inter != null) {
	      intersections.add(inter);
	      if (intersections.size()<2) { vertices[0]=i; vertices[1]=i+1; }
	      else { vertices[2]=i; vertices[3]=i+1; }
	    }
	  }
	}
	
	public static PVector lineSegmentIntersection(
			  float Ax, float Ay,
			  float Bx, float By,
			  float Cx, float Cy,
			  float Dx, float Dy) 
			 {

			  float  distAB, theCos, theSin, newX, ABpos ;
			  float X; float Y;

			  //  Fail if either line is undefined.
			  if (Ax==Bx && Ay==By || Cx==Dx && Cy==Dy) return null;

			  //  (1) Translate the system so that point A is on the origin.
			  Bx-=Ax; By-=Ay;
			  Cx-=Ax; Cy-=Ay;
			  Dx-=Ax; Dy-=Ay;

			  //  Discover the length of segment A-B.
			  distAB=PApplet.sqrt(Bx*Bx+By*By);

			  //  (2) Rotate the system so that point B is on the positive X axis.
			  theCos=Bx/distAB;
			  theSin=By/distAB;
			  newX=Cx*theCos+Cy*theSin;
			  Cy  =Cy*theCos-Cx*theSin; Cx=newX;
			  newX=Dx*theCos+Dy*theSin;
			  Dy  =Dy*theCos-Dx*theSin; Dx=newX;

			  //  Fail if the lines are parallel.
			  //if (Cy==Dy) return null;
			  //  Fail if segment C-D doesn't cross line A-B.
			  if (Cy<0 && Dy<0 || Cy>=0 && Dy>=0) return null;

			  //  (3) Discover the position of the intersection point along line A-B.
			  ABpos=Dx+(Cx-Dx)*Dy/(Dy-Cy);
			  
			  //  Fail if segment C-D crosses line A-B outside of segment A-B.
			  if (ABpos<0 || ABpos>distAB) return null;

			  //  (4) Apply the discovered position to line A-B in the original coordinate system.
			  X=Ax+ABpos*theCos;
			  Y=Ay+ABpos*theSin;

			  //  Success.
			  return new PVector(X,Y); 
			}

			PVector lineIntersection_(
			  float Ax, float Ay,
			  float Bx, float By,
			  float Cx, float Cy,
			  float Dx, float Dy) 
			 {

			  float  distAB, theCos, theSin, newX, ABpos ;
			  float X; float Y;

			  //  Fail if either line is undefined.
			  if (Ax==Bx && Ay==By || Cx==Dx && Cy==Dy) return null;

			  //  (1) Translate the system so that point A is on the origin.
			  Bx-=Ax; By-=Ay;
			  Cx-=Ax; Cy-=Ay;
			  Dx-=Ax; Dy-=Ay;

			  //  Discover the length of segment A-B.
			  distAB=PApplet.sqrt(Bx*Bx+By*By);

			  //  (2) Rotate the system so that point B is on the positive X axis.
			  theCos=Bx/distAB;
			  theSin=By/distAB;
			  newX=Cx*theCos+Cy*theSin;
			  Cy  =Cy*theCos-Cx*theSin; Cx=newX;
			  newX=Dx*theCos+Dy*theSin;
			  Dy  =Dy*theCos-Dx*theSin; Dx=newX;

			  //  Fail if the lines are parallel.
			  if (Cy==Dy) return null;

			  //  (3) Discover the position of the intersection point along line A-B.
			  ABpos=Dx+(Cx-Dx)*Dy/(Dy-Cy);

			  //  (4) Apply the discovered position to line A-B in the original coordinate system.
			  X=Ax+ABpos*theCos;
			  Y=Ay+ABpos*theSin;

			  //  Success.
			  return new PVector(X,Y); 
			}
	
	//void DistanceFromLine(double cx, double cy, double ax, double ay ,
			  //double bx, double by, double &distanceSegment,
			  //double &distanceLine)
	public float[] DistanceFromLine(float cx, float cy, float ax, float ay ,
			float bx, float by)
	{

//
// find the distance from the point (cx,cy) to the line
// determined by the points (ax,ay) and (bx,by)
//
// distanceSegment = distance from the point to the line segment
// distanceLine = distance from the point to the line (assuming
//					infinite extent in both directions
//

/*

Subject 1.02: How do I find the distance from a point to a line?


Let the point be C (Cx,Cy) and the line be AB (Ax,Ay) to (Bx,By).
Let P be the point of perpendicular projection of C on AB.  The parameter
r, which indicates P's position along AB, is computed by the dot product 
of AC and AB divided by the square of the length of AB:

(1)     AC dot AB
r = ---------  
  ||AB||^2

r has the following meaning:

r=0      P = A
r=1      P = B
r<0      P is on the backward extension of AB
r>1      P is on the forward extension of AB
0<r<1    P is interior to AB

The length of a line segment in d dimensions, AB is computed by:

L = sqrt( (Bx-Ax)^2 + (By-Ay)^2 + ... + (Bd-Ad)^2)

so in 2D:   

L = sqrt( (Bx-Ax)^2 + (By-Ay)^2 )

and the dot product of two vectors in d dimensions, U dot V is computed:

D = (Ux * Vx) + (Uy * Vy) + ... + (Ud * Vd)

so in 2D:   

D = (Ux * Vx) + (Uy * Vy) 

So (1) expands to:

  (Cx-Ax)(Bx-Ax) + (Cy-Ay)(By-Ay)
r = -------------------------------
                L^2

The point P can then be found:

Px = Ax + r(Bx-Ax)
Py = Ay + r(By-Ay)

And the distance from A to P = r*L.

Use another parameter s to indicate the location along PC, with the 
following meaning:
 s<0      C is left of AB
 s>0      C is right of AB
 s=0      C is on AB

Compute s as follows:

  (Ay-Cy)(Bx-Ax)-(Ax-Cx)(By-Ay)
s = -----------------------------
              L^2


Then the distance from C to P = |s|*L.

*/
		float[] res = new float[3]; // xy of intersection point, distance to intersection

		float r_numerator = (cx-ax)*(bx-ax) + (cy-ay)*(by-ay);
		float r_denomenator = (bx-ax)*(bx-ax) + (by-ay)*(by-ay);
		float r = r_numerator / r_denomenator;
		//
		float px = ax + r*(bx-ax);  // the intersection point
		float py = ay + r*(by-ay);
		//
		float s =  ((ay-cy)*(bx-ax)-(ax-cx)*(by-ay) ) / r_denomenator;

		//distanceLine = fabs(s)*sqrt(r_denomenator);
		float distanceLine = p.abs(s)*p.sqrt(r_denomenator);

		//
		//(xx,yy) is the point on the lineSegment closest to (cx,cy)
		//
		float xx = px;
		float yy = py;
		float distanceSegment; // // //
		if ( (r >= 0) && (r <= 1) )
		{
			distanceSegment = distanceLine;
		}
			else
		{

				float dist1 = (cx-ax)*(cx-ax) + (cy-ay)*(cy-ay);
				float dist2 = (cx-bx)*(cx-bx) + (cy-by)*(cy-by);
				if (dist1 < dist2)
				{
					xx = ax;
					yy = ay;
					distanceSegment = p.sqrt(dist1);
				}
				else
				{
					xx = bx;
					yy = by;
					distanceSegment = p.sqrt(dist2);
				}


		}
		res[0] = xx;
		res[1] = yy;
		res[2] = distanceSegment;
		return res;
	}
	
	public int WeightedDrawf(Vector<Float> weights)  //general weighted draw on a vector with weights
	{
	    float totalweight = 0;
	    float weight;
	    for (int i = 0; i < weights.size(); i++)
	    {
	      weight = (Float)weights.elementAt(i);
	      totalweight += weight*100; 
	    }
	    
	    if (totalweight==0) return -1;
	    
	    float hit = 0;
	    float r = p.random(totalweight);
	    for (int i = 0; i < weights.size(); i++)
	    {
	      weight = (Float)weights.elementAt(i);
	      hit += weight*100; 
	      if (hit >= r) return i;
	    }
	    return -1;
	}
	public int WeightedDrawf(Vector<Float> weights, int indexToIngnore)  //general weighted draw on a vector with weights
	{
	    float totalweight = 0;
	    float weight;
	    for (int i = 0; i < weights.size(); i++)
	    {
	    	if (i==indexToIngnore) continue;
	    	weight = (Float)weights.elementAt(i);
	    	totalweight += weight*100; 
	    }
	    
	    if (totalweight==0) return -1;
	    
	    float hit = 0;
	    float r = p.random(totalweight);
	    for (int i = 0; i < weights.size(); i++)
	    {
	    	if (i==indexToIngnore) continue;
	    	weight = (Float)weights.elementAt(i);
	    	hit += weight*100; 
	    	if (hit >= r) return i;
	    }
	    return -1;
	}

	
}
