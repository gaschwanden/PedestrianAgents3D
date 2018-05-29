import java.util.Vector;

import processing.core.PApplet;
import processing.core.PVector;
import utility.MyMath;


public class Isovist {
	PVector origin;
	Vector<PVector> rays;
	Landmark[] hitTest;
	float radDev = 0.01f;
	PApplet p;
	Scene scene;
	float isoZ = 0.01f;
	  
	//boolean needsInit = false;
	int nextX;
	int nextY;
	
	MyMath myMath;
	
	boolean made = false;
	   
	Isovist (PApplet _p, Scene s, float x, float y)
	{
		scene = s;
		p=_p;
		myMath = new MyMath(p);
	    init(x,y); 
	}
	void init(float x, float y) {
	    origin = new PVector();
	    origin.x = x; origin.y = y;
	    rays = new Vector<PVector>();
	    hitTest = new Landmark[1000];  // make larger than necessary....
	    for (int i = 0; i < hitTest.length; i++ ) {
	    	hitTest[i] = null;
	    }
	    made = false;
	    //make();
	}
	void draw()
	{
		if (!made) return;
	    //if (needsInit)  //never init the isovist out of an event handler!
	    //{
	      //needsInit = false;
	     // init(nextX, nextY);
	    //}
	    p.noStroke();
	    //point (origin.x, origin.y, 10);
	    p.fill(0);
	    p.pushMatrix();
	    p.translate(origin.x,origin.y,isoZ+0.2f);
	      p.ellipse(0,0,scene.gridsize ,scene.gridsize);
	    p.popMatrix();
	    PVector d;
	    Landmark lm;
	    p.stroke(255,255,0);
	    
	    for (int i = 0; i < rays.size(); i++)
	    {
	      d = rays.get(i);
	      lm = hitTest[i];
	      if (lm==null) p.stroke(255,255,0);
	      else p.stroke(255,0,0);
	      p.line(origin.x, origin.y, isoZ, d.x,d.y, isoZ);
	    }
	}
	  
	void make()
	{
		if (made) return;
		
	    float angle = 0;
	    float x = 0; float y = 0;
	      
	    for(float j=angle;j <PApplet.PI*2 +angle;j+=radDev) {
	      //simply add long rays that can be cut later
	      float x1 = 0;
	      float y1 = 0;
	      float x2 = x;
	      float y2 = y;
	      int pixx=(int)origin.x;
	      int pixy=(int)origin.y;
	      
	      x= p.width * PApplet.cos(j)  *100; // // 
	      y = p.width * PApplet.sin(j) *100; // // 
	      pixx = (int) (origin.x + x);
	      pixy = (int) (origin.y + y);
	      
	        
	      PVector d = new PVector();
	      d.x=pixx;
	      d.y=pixy;
	      rays.add(d);
	     
	    }  //end add rays
	    
	    for (int i = 0; i < hitTest.length; i++ ) {
	    	hitTest[i] = null;
	    }
	   
	    
	 
	    
	    //cut rays
	    PVector r;
	    PVector a,b;
	    float A1,A2,B1,B2,C1,C2;
	    for (int i =0 ; i < rays.size(); i++) {
	    //for (int i =0 ; i < 1; i++) {
	      r = rays.get(i); 

	      //loop through all the polygon vertices
	      if (scene.buildings!=null) {
		      for (int j = 0; j < scene.buildings.size(); j++)
		      {
		        Building p = scene.buildings.elementAt(j);
		        if (p == null) continue;
		        if (p.footprint == null) continue;
		        if (p.footprint.vertices.size()==0) continue;
		        
		        // 
		        //off ground?
		        if (p.footprint.vertices.elementAt(0).z >1.1f) continue;	
		        
		        //check against the bounding rectangle
		        if (origin.x>p.footprint.maxX && r.x>p.footprint.maxX) continue; 
		        if (origin.y>p.footprint.maxY && r.y>p.footprint.maxY) continue;
		        if (origin.x<p.footprint.minX && r.x<p.footprint.minX) continue; 
		        if (origin.y<p.footprint.minY && r.y<p.footprint.minY) continue;
		      
		        
		        //if (p.InsertionPoint.z > 0) continue;           //disregard buildings that are off the ground
		        
		        for (int k = 0; k < p.footprint.vertices.size(); k++) {
		          a = (PVector)p.footprint.vertices.elementAt(k);
		          if (k < p.footprint.vertices.size()-1) b = (PVector)p.footprint.vertices.elementAt(k+1);
		          else b = (PVector)p.footprint.vertices.elementAt(0);
		          
		          PVector inter = myMath.lineSegmentIntersection(origin.x, origin.y, r.x, r.y, a.x, a.y, b.x, b.y);
		          if (inter == null)  {
		            //println("katz");
		          }
		          else {
		            //println(inter.x+" "+inter.y);
		            r.set(inter);
		            hitTest[i] = null;
		          }
		        }
		      }
	      }
	      // end buildings
	      
	    //loop through all the obstacles vertices
	      if (scene.obstacles!=null) {
		      for (int j = 0; j < scene.obstacles.size(); j++)
		      {
		        Building p = scene.obstacles.elementAt(j);
		        if (p == null) continue;
		        //if (p.dxfLayer.equals("OBSTACLES_LOW")) continue;
		        if (p.dxfLayer.equals("WATERBODY")) continue;
		        if (p.dxfLayer.equals("STREETS")) continue;
		        
		        //check against the bounding rectangle
		        if (origin.x>p.footprint.maxX && r.x>p.footprint.maxX) continue; 
		        if (origin.y>p.footprint.maxY && r.y>p.footprint.maxY) continue;
		        if (origin.x<p.footprint.minX && r.x<p.footprint.minX) continue; 
		        if (origin.y<p.footprint.minY && r.y<p.footprint.minY) continue;
		      
		        
		        //if (p.InsertionPoint.z > 0) continue;           //disregard buildings that are off the ground
		        
		        for (int k = 0; k < p.footprint.vertices.size(); k++) {
		          a = (PVector)p.footprint.vertices.elementAt(k);
		          if (k < p.footprint.vertices.size()-1) b = (PVector)p.footprint.vertices.elementAt(k+1);
		          else b = (PVector)p.footprint.vertices.elementAt(0);
		          
		          PVector inter = myMath.lineSegmentIntersection(origin.x, origin.y, r.x, r.y, a.x, a.y, b.x, b.y);
		          if (inter == null)  {
		            //println("katz");
		          }
		          else {
		            //println(inter.x+" "+inter.y);
		            r.set(inter);
		            hitTest[i] = null;
		          }
		        }
		      }
	      }
	      // end obstacles
	      
	      // landmarks
	      if (scene.landmarks!=null) {
		      for (int j = 0; j < scene.landmarks.size(); j++)
		      {
		        Landmark p = scene.landmarks.elementAt(j);
		        if (p == null) continue;
		        
		        //check against the bounding rectangle
		        for (int ii = 0; ii < p.footprints.size(); ii++) { 
		        	Footprint footprint = p.footprints.elementAt(ii);
			        if (origin.x>footprint.maxX && r.x>footprint.maxX) continue; 
			        if (origin.y>footprint.maxY && r.y>footprint.maxY) continue;
			        if (origin.x<footprint.minX && r.x<footprint.minX) continue; 
			        if (origin.y<footprint.minY && r.y<footprint.minY) continue;
			      
			       // System.out.println("katx");
			        //if (p.InsertionPoint.z > 0) continue;           //disregard buildings that are off the ground
			        
			        for (int k = 0; k < footprint.vertices.size(); k++) {
			          a = (PVector)footprint.vertices.elementAt(k);
			          if (k < footprint.vertices.size()-1) b = (PVector)footprint.vertices.elementAt(k+1);
			          else b = (PVector)footprint.vertices.elementAt(0);
			          
			          PVector inter = myMath.lineSegmentIntersection(origin.x, origin.y, r.x, r.y, a.x, a.y, b.x, b.y);
			          if (inter == null)  {
			            //println("katz");
			          }
			          else {
			            r.set(inter);
			            hitTest[i] = p;
			          }
			        }
		        }
		      }
	      }
	    }
	    made = true;
	  }

}
