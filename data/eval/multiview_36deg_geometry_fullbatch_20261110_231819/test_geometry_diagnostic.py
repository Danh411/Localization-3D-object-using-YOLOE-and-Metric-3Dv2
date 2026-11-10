import unittest,math,numpy as np
from ground import floor_z,fit_scale
from methods import geomedian,huber,consensus

class GeometryTests(unittest.TestCase):
    def test_axial_and_invalid_rays(self):
        ray=np.array([[0,.5,1],[0,.25,1],[0,0,1],[0,-.5,1],[0,.02,1]])
        z,ok=floor_z(ray,np.array([0,-1,0]),1.)
        np.testing.assert_allclose(z[:2],[2,4])
        self.assertEqual(ok.tolist(),[True,True,False,False,False])
    def test_noisy_height_scales_axial_depth(self):
        z,ok=floor_z(np.array([[0,.5,1]]),np.array([0,-1,0]),1.02)
        self.assertTrue(ok[0]); self.assertAlmostEqual(z[0],2.04)
    def test_block_scale_and_fallback(self):
        z=np.full((160,160),2.)
        ok=np.ones(z.shape,bool)
        scale,*_,status=fit_scale(ok,z/1.4,z,ok)
        self.assertEqual(status,'accepted'); self.assertAlmostEqual(scale,1.4)
        scale,*_,status=fit_scale(~ok,z,z,ok)
        self.assertEqual(status,'pixels'); self.assertAlmostEqual(scale,1.)
    def test_robust_point_and_ransac_rejects_few_views(self):
        x=np.array([[0.,0,0],[.01,0,0],[.02,0,0],[1.,0,0]])
        w=np.ones(4)
        self.assertLess(geomedian(x,w)[0],.03)
        self.assertLess(huber(x,w)[0],.06)
        self.assertIsNone(consensus(x,w,np.zeros(4))[0])
        center,*_=consensus(x,w,np.radians([1,21,41,61]))
        self.assertAlmostEqual(center[0],.01)

if __name__=='__main__':
    unittest.main()

