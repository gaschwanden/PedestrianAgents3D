package utility;
import processing.core.PApplet;
import processing.core.PMatrix3D;
import processing.core.PVector;
import processing.opengl.PGraphicsOpenGL;


public class MyGL {
	PApplet p;
	public MyGL(PApplet _p)
	{
		p=_p;
	}

	public PVector unprojectScreenCoords(PGraphicsOpenGL g3d, float winX, float winY, float winZ, float winwidth, float winheight) {
		

		  PMatrix3D mView     = g3d.modelview.get();
		  PMatrix3D mProj     = g3d.projection.get(); 

		 
		  //printM(mView, "Model View"); //
		  mProj.apply(mView);
		  mProj.invert();

		  float[] result = new float[4];
		  float[] factor = new float[]{  ((2.0f * winX)  / winwidth)  -1.0f,
		                                 ((2.0f * winY)  / winheight) -1.0f, //screenH - y?
		                                 ( 2.0f * winZ) -1.0f ,
		                                   1.0f,};
		  mProj.mult(factor, result);

		            
		  result[0] /= result[3];
		  result[1] /= result[3];
		  result[2] /= result[3];
		  result[3] /= result[3];
		           
		  //println(new PVector(result[0],result[1],result[2]));
		  return new PVector(result[0],result[1],result[2]);
	}
	
	public PVector projectRayToXYPlane(PVector eye3D, PVector Ray, float elevation)
	////////////////////////////////////////////////////////////
	//given a ray and an eye position (in space), 
	//calculate the intersection point of the ray 
	//with a horizontal plane at elevation level
	////////////////////////////////////////////////////////////
	{
		if (Ray.z==0) return null;  //no intersection with a horizontal plane

		float n = (elevation - eye3D.z) / Ray.z;
		float y = eye3D.y + n*Ray.y;
		float x = eye3D.x + n*Ray.x;

		return new PVector(x,y,elevation);
	}

	public int projectScreenCoords(PGraphicsOpenGL g3d, float objx, float objy, float objz, float windowCoordinate[], float winW, float winH) //, PMatrix3D modelview, PMatrix3D projection, float windowCoordinate[])
	{
	  // project a point to screen
	  int retval = 1;
	  
	  PMatrix3D modelview      = g3d.modelview.get();
	  PMatrix3D projection     = g3d.projection.get(); 

	  
	  float fTempo[] = new float[8];
	  //Modelview transform
                       
	  fTempo[0]=modelview.m00*objx+modelview.m01*objy+modelview.m02*objz+modelview.m03;  //w is always 1
	  fTempo[1]=modelview.m10*objx+modelview.m11*objy+modelview.m12*objz+modelview.m13;
	  fTempo[2]=modelview.m20*objx+modelview.m21*objy+modelview.m22*objz+modelview.m23;
	  fTempo[3]=modelview.m30*objx+modelview.m31*objy+modelview.m32*objz+modelview.m33;
	                              
	  
	  //Projection transform, the final row of projection matrix is always [0 0 -1 0]
	  //so we optimize for that.
	  fTempo[4]=projection.m00*fTempo[0]+projection.m01*fTempo[1]+projection.m02*fTempo[2]+projection.m03*fTempo[3];
	  fTempo[5]=projection.m10*fTempo[0]+projection.m11*fTempo[1]+projection.m12*fTempo[2]+projection.m13*fTempo[3];
	  fTempo[6]=projection.m20*fTempo[0]+projection.m21*fTempo[1]+projection.m22*fTempo[2]+projection.m23*fTempo[3];
	  fTempo[7]=-fTempo[2];
	  //The result normalizes between -1 and 1
	  //if(fTempo[7]==0.0)	//The w value
	     //{  println("problem in projectscreencoord??"); return 0; }
	  
	  fTempo[7]=1.0f/fTempo[7];
	  //Perspective division
	  fTempo[4]*=fTempo[7];
	  fTempo[5]*=fTempo[7];
	  fTempo[6]*=fTempo[7];
	  //Window coordinates
	  //Map x, y to range 0-1
	  windowCoordinate[0]=(fTempo[4]*0.5f+0.5f) * winW;
	  windowCoordinate[1]=(fTempo[5]*0.5f+0.5f) * winH;
	  //This is only correct when glDepthRange(0.0, 1.0)
	  windowCoordinate[2]=(1.0f+fTempo[6])*0.5f;	//Between 0 and 1
	  return retval;
	}
	
	private void printM(PMatrix3D m, String name)
	{
	  p.println();
	  p.println(name);
	  p.println(m.m00+" "+m.m01+" "+m.m02+" "+m.m03);
	  p.println(m.m10+" "+m.m11+" "+m.m12+" "+m.m13);
	  p.println(m.m20+" "+m.m21+" "+m.m22+" "+m.m23);
	  p.println(m.m30+" "+m.m31+" "+m.m32+" "+m.m33);
	}

}


