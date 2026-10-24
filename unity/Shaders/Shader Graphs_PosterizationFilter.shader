Shader "Shader Graphs/PosterizationFilter"
{
	// Pass-through replacement for an unrecoverable Shader Graph full-screen effect (macOS rebuild).
	Properties {
		Vector1_81FC5D70 ("PosterizedConut", Float) = 0
		_Color ("Color", Vector) = (0,0,0,0)
	}
	HLSLINCLUDE
	#pragma vertex Vert
	#pragma target 4.5
	#pragma only_renderers d3d11 playstation xboxone xboxseries vulkan metal switch
	#include "Packages/com.unity.render-pipelines.high-definition/Runtime/RenderPipeline/RenderPass/CustomPass/CustomPassCommon.hlsl"
	float _Alpha; float4 _Color;
	float4 FullScreenPass(Varyings varyings) : SV_Target
	{
		UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(varyings);
		float3 color = CustomPassLoadCameraColor(varyings.positionCS.xy, 0);
		// pass-through
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
