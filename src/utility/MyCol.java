package utility;

import processing.core.PApplet;

public class MyCol {
	public static int[] RedYellowGreen2(float maxval, float val, PApplet p ) {
	     int []c = new int[3];        
	     float splitter = maxval/2;
	     float splitter2 = maxval/4*3;
	     if (val<=splitter) {
	                 float g = p.map(val, 0, splitter, 30, 100);
	                 //c= color(0,g,0);
	                 c[0] = 0; c[1]=(int) g; c[2]=0;
	     }
	     else if (val>splitter && val<splitter2){
	                 float r = p.map(val, splitter, splitter2, 0, 255);
	                 //c=color(r,100+(r/4),0); 
	                 c[0] = (int) r; c[1]=(int)(100.0f+(r/4.0f)); c[2]=0;
	     }
	     else {
	                 float r = p.map(val, splitter2, maxval, 0, 200);
	                 //c=color(255,200-(r/4),0);
	                 c[0] = 255; c[1]=(int)(100.0f-(r/4.0f)); c[2]=0;
	                 p.strokeWeight(3);
	                // p.println(c);
	     }
	     return c;
	}
	
	public static int[] RedWhiteBlue(float maxval, float val, PApplet p  ) {
		 int []c = new int[3];          
	     float splitter = maxval/4;
	     float splitter2 = maxval/2;
	     if (val<splitter) {
	                 float g = p.map(val, 0, splitter, 0, 105);
	                 //c= color(0,80,150+g);
	                 c[0] = 0; c[1]=80; c[2]=(int)(150+g);
	     }
	     else if (val>splitter && val<splitter2){
	                 float r = p.map(val, splitter, splitter2, 80, 255);
	                 float r1 = p.map(val, splitter, splitter2, -80, 255);
	                 //c=color(r1,r,255);
	                 c[0] = (int)r1; c[1]=(int) r; c[2]=255;
	                 
	     }
	     else {
	                 float r = p.map(val, splitter2, maxval, 0, 255);
	                 //c=color(255,255,255-r);
	                 c[0] = 255; c[1]=(int)(255-r); c[2]=(int)(255-r);
	                 p.strokeWeight(3);
	                 if (r>100) p.strokeWeight(4);
	     }
	     return c;
	}
	
	public void cylinder(float w, float h, int sides, boolean drawTop, boolean drawBottom, PApplet p)
	{
	  float angle;
	  float[] x = new float[sides+1];
	  float[] z = new float[sides+1];
	 
	  //get the x and z position on a circle for all the sides
	  for(int i=0; i < x.length; i++){
	    angle = p.TWO_PI / (sides) * i;
	    x[i] = p.sin(angle) * w;
	    z[i] = p.cos(angle) * w;
	  }
	 
	  //draw the top of the cylinder
	  if (drawTop) { // drawing this enormously takes away framerates
		  p.beginShape(p.TRIANGLE_FAN);
		 
		  p.vertex(0,   -h/2,    0);
		 
		  for(int i=0; i < x.length; i++){
			  p.vertex(x[i], -h/2, z[i]);
		  }
		 
		  p.endShape();
	  }
	 
	  //draw the center of the cylinder
	  p.beginShape(p.QUAD_STRIP); 
	 
	  for(int i=0; i < x.length; i++){
		  p.vertex(x[i], -h/2, z[i]);
		  p.vertex(x[i], h/2, z[i]);
	  }
	 
	  p.endShape();
	 
	  //draw the bottom of the cylinder
	  if (!drawBottom) return;   // drawing this enormously takes away framerates
	  p.beginShape(p.TRIANGLE_FAN); 
	 
	  p.vertex(0,   h/2,    0);
	 
	  for(int i=0; i < x.length; i++){
		  p.vertex(x[i], h/2, z[i]);
	  }
	 
	  p.endShape();
	}

}
