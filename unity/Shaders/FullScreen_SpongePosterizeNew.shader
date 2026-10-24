Shader "FullScreen/SpongePosterizeNew"
{
	// Reconstruction of Lethal Company's full-screen outline/posterize custom pass for the macOS rebuild.
	// The original Shader Graph is not recoverable from the build; property names are kept so the
	// shipped material values still apply.
	Properties {
		_OutlineThickness ("OutlineThickness", Float) = 0.001
		_DepthThreshold ("DepthThreshold", Float) = 0.4
		_DepthCurve ("DepthCurve", Float) = 0.4
		_DepthStrength ("DepthStrength", Float) = 6
		_ColorThreshold ("ColorThreshold", Float) = 0.47
		_ColorCurve ("ColorCurve", Float) = 2.94
		_ColorStrength ("ColorStrength", Float) = 0.65
	}

	HLSLINCLUDE
	#pragma vertex Vert
	#pragma target 4.5
	#pragma only_renderers d3d11 playstation xboxone xboxseries vulkan metal switch
	#include "Packages/com.unity.render-pipelines.high-definition/Runtime/RenderPipeline/RenderPass/CustomPass/CustomPassCommon.hlsl"

	float _OutlineThickness, _DepthThreshold, _DepthCurve, _DepthStrength, _ColorThreshold, _ColorCurve, _ColorStrength;

	float LinearDepthAt(float2 pixel)
	{
		pixel = clamp(pixel, 0, _ScreenSize.xy - 1);
		float d = LoadCameraDepth(pixel);
		return LinearEyeDepth(d, _ZBufferParams);
	}

	float LumaAt(float2 pixel)
	{
		pixel = clamp(pixel, 0, _ScreenSize.xy - 1);
		float3 c = CustomPassLoadCameraColor(pixel, 0);
		return Luminance(c);
	}

	float4 FullScreenPass(Varyings varyings) : SV_Target
	{
		UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(varyings);
		float2 p = varyings.positionCS.xy;
		float3 color = CustomPassLoadCameraColor(p, 0);

		float o = max(1.0, _OutlineThickness * _ScreenSize.y);
		float d0 = LinearDepthAt(p);
		float dd = 0;
		dd = max(dd, abs(LinearDepthAt(p + float2( o, 0)) - d0));
		dd = max(dd, abs(LinearDepthAt(p + float2(-o, 0)) - d0));
		dd = max(dd, abs(LinearDepthAt(p + float2(0,  o)) - d0));
		dd = max(dd, abs(LinearDepthAt(p + float2(0, -o)) - d0));
		float depthEdge = pow(saturate(dd / max(d0 * _DepthThreshold, 1e-4)), max(_DepthCurve, 1e-3)) * _DepthStrength;

		float l0 = LumaAt(p);
		float dl = 0;
		dl = max(dl, abs(LumaAt(p + float2( o, 0)) - l0));
		dl = max(dl, abs(LumaAt(p + float2(-o, 0)) - l0));
		dl = max(dl, abs(LumaAt(p + float2(0,  o)) - l0));
		dl = max(dl, abs(LumaAt(p + float2(0, -o)) - l0));
		float colorEdge = pow(saturate(dl / max(_ColorThreshold, 1e-4)), max(_ColorCurve, 1e-3)) * _ColorStrength;

		float edge = saturate(depthEdge + colorEdge);
		color *= (1.0 - edge);
		return float4(color, 1);
	}
	ENDHLSL

	SubShader
	{
		Tags { "RenderPipeline" = "HDRenderPipeline" }
		Pass
		{
			Name "Custom Pass 0"
			ZWrite Off
			ZTest Always
			Blend Off
			Cull Off
			HLSLPROGRAM
				#pragma fragment FullScreenPass
			ENDHLSL
		}
	}
	Fallback Off
}
