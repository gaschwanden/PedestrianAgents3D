package utility;

public class DXFLine {
	public DXFLine()
	{
		
	}
	public DXFLine(DXFLine l) {
		layer = l.layer;
		x1 = l.x1;
		y1 = l.y1;
		z1 = l.z1;
		x2 = l.x2;
		y2 = l.y2;
		z2 = l.z2;
	}
	public float x1,y1,z1,x2,y2,z2;
	public String layer;
	public void move(float xoffs, float yoffs, float zoffs) {
		x1+=xoffs;
		x2+=xoffs;
		y1+=yoffs;
		y2+=yoffs;
		z1+=zoffs;
		z2+=zoffs;
	}
}