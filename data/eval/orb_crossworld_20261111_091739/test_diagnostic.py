import unittest
import numpy as np
from orb import check_point,representative,Match
from experiment import pick,observation
from ground import floor_z,fit_scale

class Geometry(unittest.TestCase):
    def test_triangulates_metric_point(self):
        K=np.array([[900,0,640],[0,900,360],[0,0,1]])
        t=np.zeros(3); u=np.array([.04,0,0])
        P=K@np.column_stack((np.eye(3),-t))
        Q=K@np.column_stack((np.eye(3),-u))
        z,reason=check_point(P,Q,t,u,(640,360),(616,360),900)
        self.assertEqual(reason,'ok')
        np.testing.assert_allclose(z[0],[0,0,1.5],atol=1e-8)
        bad,reason=check_point(P,Q,t,u,(640,360),(616,376),900)
        self.assertIsNone(bad)
        self.assertEqual(reason,'reprojection')
        bad,_=check_point(P,P,t,t,(640,360),(640,360),900)
        self.assertIsNone(bad)
    def test_robust_representative_and_duplicate_gate(self):
        mask=np.zeros((80,80),bool); mask[20:61,20:61]=True
        K=(100.,100.,40.,40.)
        m=[Match(np.array([(i-4)/100,0,1.4]),i,(24+4*i,40),.2,.5) for i in range(10)]
        estimate,why=representative(m,np.eye(3),np.zeros(3),K,mask)
        self.assertEqual(why,'accepted')
        self.assertAlmostEqual(estimate['z'],1.4)
        np.testing.assert_allclose(estimate['B'],[0,0,1.4],atol=1e-8)
        self.assertIsNone(representative([m[0]]*20,np.eye(3),np.zeros(3),K,mask)[0])
    def test_ground_projection_and_missing_pixels(self):
        ray=np.array([[0,.5,1],[0,0,1],[0,-.2,1]])
        z,ok=floor_z(ray,np.array([0,-1,0]),1.1)
        self.assertAlmostEqual(z[0],2.2)
        self.assertEqual(ok.tolist(),[True,False,False])
        mat=np.ones((160,160),float)*2.2
        allowed=np.ones(mat.shape,bool)
        scale,*_,why=fit_scale(allowed,mat/1.3,mat,allowed)
        self.assertEqual(why,'accepted')
        self.assertAlmostEqual(scale,1.3)
        scale,*_,why=fit_scale(allowed,np.full_like(mat,np.nan),mat,allowed)
        self.assertEqual((scale,why),(1.,'pixels'))
    def test_fallback_requires_valid_source(self):
        self.assertEqual(pick(3,2,1,'few','unavailable')[:2],(3,'ORB'))
        self.assertEqual(pick(None,2,1,'few','accepted')[:2],(2,'GROUND'))
        self.assertEqual(pick(None,None,1,'few','unavailable')[:2],(1,'METRIC3D'))
        missing=pick(None,None,None,'few','unavailable')
        self.assertEqual(missing[:2],(None,'UNAVAILABLE'))
        self.assertIn('metric3d:missing',missing[2])

if __name__=='__main__':
    unittest.main()

