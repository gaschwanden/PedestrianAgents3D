package utility;

import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;

public class DXFMesh {
	public Vector <DXFVertex> vertices;
	public Vector <DXFFace> faces;
	
	public Vector <DXFFace> bottomfaces;  // the ones on the bottom of the object
	public Vector<DXFVertex> footprint;   // the final footprint
	
	public String layer;
	public boolean horizontal = false;
	
	public int flag = 0; 
	
	public float minz;
	public float maxz;
	float minx;
	float miny;
	float maxx;
	float maxy;
	public DXFMesh()
	{
		vertices = new Vector<DXFVertex>();
		faces = new Vector<DXFFace>();
	}
	public void setMinMaxZValue() {
		minz = 999999999f;
		maxz = -999999999f;
		for (int i = 0; i < vertices.size(); i++) {
			if (vertices.elementAt(i).z > maxz) maxz = (float)vertices.elementAt(i).z;
			if (vertices.elementAt(i).z < minz) minz = (float)vertices.elementAt(i).z;
		}
		//System.out.println(minz +" "+maxz);
	}
	
	public void setBottomFaces()
	{
		bottomfaces = new Vector<DXFFace>();
		float thres = 0.1f;
		for (int i = 0; i < faces.size(); i++) {
			DXFFace f = faces.elementAt(i);
			boolean isBottom = true;
			for (int j = 0; j < f.vertices.size(); j++) {
				if (PApplet.abs((float) (f.vertices.elementAt(j).z - minz)) > thres) {
					isBottom = false; break;
				}
			}
			if (isBottom) bottomfaces.addElement(f);
		}
	}
	public void joinBottomFaces() {
		if (bottomfaces.size()==0) return;
		
		footprint = new Vector<DXFVertex>();
		
		DXFFace f = bottomfaces.firstElement();
		bottomfaces.remove(0);
		
		for (int i = 0; i < f.vertices.size(); i++) {
			DXFVertex v = f.vertices.elementAt(i);
			footprint.addElement(new DXFVertex(v));
		}
		
		boolean success = true;
		while (success && bottomfaces.size()>0) {
			success = false;
			for (int i = 0; i < bottomfaces.size(); i++) {
				DXFFace ff = bottomfaces.elementAt(i);
				if (join(ff, footprint)) {
					success = true;
					bottomfaces.remove(i);
					break;
				}
			}
		}
		//System.out.println(bottomfaces.size());
		//System.out.println(footprint.size());
		if (bottomfaces.size() > 0) System.out.println("DXF Mesh import: There was a problem joining the triangles to a coherent footprint");
	}
	private boolean join(DXFFace ff, Vector<DXFVertex> fp) {
		float thres = 0.01f;
		int lenfp = fp.size();
		int lenff = ff.vertices.size();
		for (int i = 0; i < fp.size(); i++) {
			DXFVertex v1 = fp.elementAt(i);
			DXFVertex v2 = fp.elementAt((i+1) % lenfp);
			
			for (int j = 0; j < ff.vertices.size(); j++) {
				DXFVertex vv1 = ff.vertices.elementAt(j);
				DXFVertex vv2 = ff.vertices.elementAt((j+1) % lenff);
				
				if (PApplet.abs((float)(v1.x-vv1.x)) < thres && PApplet.abs((float)(v1.y-vv1.y)) < thres) 
				{
					if (PApplet.abs((float)(v2.x-vv2.x)) < thres && PApplet.abs((float)(v2.y-vv2.y)) < thres) {
						//System.out.println("ho "+i);
						fp.insertElementAt(ff.vertices.elementAt((j+2) % lenff), i); // lets rely on the faces being triangles
						return true; // insert and true
					}
				}
				if (PApplet.abs((float)(v1.x-vv2.x)) < thres && PApplet.abs((float)(v1.y-vv2.y)) < thres) 
				{
					if (PApplet.abs((float)(v2.x-vv1.x)) < thres && PApplet.abs((float)(v2.y-vv1.y)) < thres) {
						//System.out.println("ho2 "+i);
						fp.insertElementAt(ff.vertices.elementAt((j+2) % lenff), i+1); // lets rely on the faces being triangles
						return true; // insert and true
					}
				}
			}
		}
		//System.out.println("tri could not be inserted");
		return false;
	}
	public void scale(float scaler) {
		for (DXFVertex v : vertices) {
			v.x*=scaler;
			v.y*=scaler;
			v.z*=scaler;
		}
		
	}
	
	/*public boolean isVerticalOffset(DXFMesh other) {
		float thres = 0.1f;
		if (!horizontal) return false;
	
		if (PApplet.abs(minx - other.minx) > thres) return false;
		if (PApplet.abs(maxx - other.maxx) > thres) return false;
		if (PApplet.abs(miny - other.miny) > thres) return false;
		if (PApplet.abs(maxy - other.maxy) > thres) return false;
		
		if (vertices.size() != other.vertices.size()) return false;
		// TODO: a more thorough check...
		return true;
	}

	public void setProperties() {
		// some useful mesh properties
		horizontal = false;
		if (vertices.size()==0) return;
		
		float tres = 0.1f;
		
		horizontal = true;
		minx = 999999999f;
		miny = 999999999f;
		maxx = -999999999f;
		maxy = -999999999f;
		
		float z = vertices.firstElement().z;
		for (int i = 0; i < vertices.size(); i++) {
			if (PApplet.abs(vertices.elementAt(i).z - z) > tres) horizontal = false;
			if (vertices.elementAt(i).x>maxx) maxx = vertices.elementAt(i).x;
			if (vertices.elementAt(i).y>maxy) maxy = vertices.elementAt(i).y;
			if (vertices.elementAt(i).x<minx) minx = vertices.elementAt(i).x;
			if (vertices.elementAt(i).y<miny) miny = vertices.elementAt(i).y;
		}
		
	}*/
	
	

}
