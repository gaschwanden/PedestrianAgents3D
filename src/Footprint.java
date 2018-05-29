import java.util.Collections;
import java.util.Comparator;
import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import utility.MyMath;


public class Footprint {

	Vector <PVector> vertices;
	Vector <PVector> verticesS;
	Vector[] segpts;            					   // facade segmented by ground plane pixels
	Vector[] segs_pixrefs;							   // reference to the pixels


	float minX, minY, maxX, maxY;                      //the bounding rectangle
	float pminX, pminY, pmaxX, pmaxY;                  //the previous bounding rectangle
	float minXS, minYS, maxXS, maxYS;                  //the bounding rectangle on the screen

	PApplet p;

	float thinningTol = 0.01f;
	MyMath myMath;

	boolean needs_updateGridSegments = true;

	public Footprint(PApplet _p) 
	{
		p=_p;
		vertices  = new Vector<PVector>();
		verticesS = new Vector<PVector>();
		minX=99999999999.9f; minY=99999999999.9f; maxX=-99999999999.9f; maxY=-99999999999.9f;
		segpts = new Vector[vertices.size()];
		segs_pixrefs = new Vector[vertices.size()];
		myMath = new MyMath(p);
	}
	public void draw() {
		p.stroke(155);
		p.fill(50);
		p.beginShape();
		for (int i=0; i<vertices.size(); i++) {
			p.vertex(vertices.elementAt(i).x,   vertices.elementAt(i).y,   vertices.elementAt(i).z );
		}
		p.endShape(p.CLOSE);
	}

	public void drawFill(int col) {
		p.noStroke();
		p.fill(p.red(col), p.green(col), p.blue(col), p.alpha(col));
		p.beginShape();
		for (int i=0; i<vertices.size(); i++) {
			p.vertex(vertices.elementAt(i).x,   vertices.elementAt(i).y,   vertices.elementAt(i).z );
		}
		p.endShape(p.CLOSE);
	}


	public void addVertex(float x, float y, float z) {
		if (vertices.size()>0) {  // cleanup - if this vertex is very close to the previous, do not insert
			if (PApplet.abs(vertices.lastElement().x-x) < thinningTol) {
				if (PApplet.abs(vertices.lastElement().y-y) < thinningTol) {
					return;
				}
			}
			if (PApplet.abs(vertices.firstElement().x-x) < thinningTol) {   // /check the first element, too
				if (PApplet.abs(vertices.firstElement().y-y) < thinningTol) {
					return;
				}
			}
		}
		vertices.addElement(new PVector(x,y,z));
		verticesS.addElement(new PVector(0,0,2));   // note z>= 1 -> result not valid
		if (minX > x) minX = x;
		if (minY > y) minY = y;
		if (maxX < x) maxX = x;
		if (maxY < y) maxY = y;
	}

	public void setVertices(Vector<PVector> verts) {
		// use this to give a set of vertices to the footprint
		vertices = verts;
		for (int i=0; i<vertices.size(); i++)
		{
			verticesS.addElement(new PVector(0,0,2));
		}
		setBoundingRectangle();
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

	public void boundingToPreviousBoundingRectangle()
	{
		pminX = minX;
		pmaxX = maxX;
		pminY = minY;
		pmaxY = maxY;
	}

	/////////////////////////////////////////////////////////////////////////////////////////////////////

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

	void vertexHitTestS(int x, int y, int polyIndex, Vector nearVertices)  //vertex hit test for projected screen coordinates
	//return vector nearvertices that tcontains poly and vertex id, if any near
	{
		if (verticesS==null)            return;
		//if (screenvertices_valid==null)      return;
		//if (screenvertices_valid.size()==0)  return;

		//check against bounding rectangle
		if (x < (minXS - Scene.tol)) return;
		if (y < (minYS - Scene.tol)) return;
		if (x > (maxXS + Scene.tol)) return;
		if (y > (maxYS + Scene.tol)) return;

		PVector a,b;
		b  = new PVector(x,y);

		for (int i = 0; i < verticesS.size(); i++) {
			if ((PVector)verticesS.elementAt(i) == null) continue;  // can be null due to invalidity
			if (verticesS.elementAt(i).z >= 1)           continue;  // invalid

			a = new PVector();
			a.set((PVector)verticesS.elementAt(i));

			b.z=a.z;   // important! otherwise the distance between the 'mouse' and the edge can be too large !
			a.sub(b);

			if (a.mag() < Scene.tol){
				int[] ref = new int[2];
				ref[0] = polyIndex;
				ref[1] = i;
				nearVertices.add(ref);   //we are storing all the vertices that are close to the pointer in ref
			}
		}
	}


	//////////////////////////////////////////////////////////////////////////////////////////////////////

	void calculateGriddedSegments(Scene scene)
	{
		//calculates the intersection points of the footprint sides with the grid 
		//for a stripy display of the facades
		needs_updateGridSegments = false;

		PVector a = new PVector();
		PVector b = new PVector();
		PVector dir,p;
		int minfieldx,minfieldy,maxfieldx,maxfieldy;  //the fields the endpoints are in
		segpts 			= new Vector[vertices.size()];
		segs_pixrefs 	= new Vector[vertices.size()];

		float xx; 
		float n;
		float yy;

		for (int i = 0; i < vertices.size(); i++) 
			//for (int i = 3; i < 4; i++) 
		{
			Vector segpoints = new Vector();
			a = new PVector();
			b = new PVector();

			//get vertices and bring to grid scale

			a  = new PVector(((PVector)vertices.elementAt(i)).x,((PVector)vertices.elementAt(i)).y, 0);
			if (i < vertices.size()-1) {
				b  = new PVector(((PVector)vertices.elementAt(i+1)).x,((PVector)vertices.elementAt(i+1)).y, 0);
			}
			else 
			{
				b  = new PVector(((PVector)vertices.elementAt(0)).x,((PVector)vertices.elementAt(0)).y, 0);
			}

			segpoints.add(a);
			segpoints.add(b);

			PVector start, end;

			// x  /////////////////////////////////////////////////////////
			if (a.x < b.x)  { start=a; end=b; }
			else 			{ start=b; end=a; }

			//the dir of the segment
			dir  = new PVector(end.x,end.y);
			dir.sub(start);

			// find pix we are in
			minfieldx = scene.grid.getGridcellX(start.x);
			minfieldy = scene.grid.getGridcellY(start.y);
			maxfieldx = scene.grid.getGridcellX(end.x);
			maxfieldy = scene.grid.getGridcellY(end.y);

			float startOffs = (scene.grid.sx+minfieldx*scene.grid.gridsize  +  scene.grid.gridsize/2.0f)
					- start.x;
			xx = start.x+startOffs;
			if (xx<end.x){ 
				n =  (xx-a.x)/dir.x;
				yy = a.y + n * dir.y;
				segpoints.add(new PVector(xx, yy));
			}
			xx += scene.grid.gridsize;
			while (xx<end.x){
				n =  (xx-a.x)/dir.x;
				yy = a.y + n * dir.y;
				segpoints.add(new PVector(xx, yy));
				xx += scene.grid.gridsize;
			}

			// y ////////////////////////////////////////////////////////////// 
			if (a.y < b.y)  { start=a; end=b; }
			else 			{ start=b; end=a; }

			//the dir of the segment
			dir  = new PVector(end.x,end.y);
			dir.sub(start);

			// find pix we are in
			minfieldx = scene.grid.getGridcellX(start.x);
			minfieldy = scene.grid.getGridcellY(start.y);
			maxfieldx = scene.grid.getGridcellX(end.x);
			maxfieldy = scene.grid.getGridcellY(end.y);

			startOffs = (scene.grid.sy+minfieldy*scene.grid.gridsize  +  scene.grid.gridsize/2.0f)
					- start.y;
			yy = start.y+startOffs;
			if (yy<end.y){ 
				n =  (yy-a.y)/dir.y;
				xx = a.x + n * dir.x;
				segpoints.add(new PVector(xx, yy));
			}
			yy += scene.grid.gridsize;
			while (yy<end.y){
				n =  (yy-a.y)/dir.y;
				xx = a.x + n * dir.x;
				segpoints.add(new PVector(xx, yy));
				yy += scene.grid.gridsize;
			}
			///////////////////////////////////////////////////////////////////
			//sort the intersection points:
			//println(segpoints);
//			if (a.x != b.x)
//				Collections.sort(segpoints, new XComparator());
//			else
//				Collections.sort(segpoints, new YComparator());
//			//println(segpoints);

			///////////////////////////////////////////////////////////////////
			// now work out all the pixel refs that our facade segments are pointing to
			Vector <PixRef> pixels = new Vector<PixRef>();
			PVector pt0, pt1;
			for (int k = 1; k < segpoints.size(); k++) {
				pt0 = (PVector)segpoints.elementAt(k-1);
				pt1 = (PVector)segpoints.elementAt(k);
				int px = scene.grid.getGridcellX(pt0.x + (pt1.x-pt0.x)/2.0f);
				int py = scene.grid.getGridcellY(pt0.y + (pt1.y-pt0.y)/2.0f);
				pixels.addElement(new PixRef(px,py));
			}
			segs_pixrefs[i] = pixels;
			segpts[i] 		= segpoints;
		}
	}

//	class x implements Comparator{
//		public int compare(Object o1, Object o2) {
//			PVector a = (PVector)o1;
//			PVector b = (PVector)o2;
//
//			if (a.x==b.x) return 0;
//			if (a.x>b.x) return 1;
//			return -1;
//		}
//	}
//
//	class YComparator implements Comparator {
//		public int compare(Object o1, Object o2) {
//			PVector a = (PVector)o1;
//			PVector b = (PVector)o2;
//
//			if (a.y==b.y) return 0;
//			if (a.y>b.y) return 1;
//			return -1;
//		}
	}








