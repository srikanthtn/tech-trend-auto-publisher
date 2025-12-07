import requests

def get_instagram_account_id(access_token):
    """
    Try to fetch the Instagram Business Account ID associated with the access token.
    Assumes the token is a User Access Token with 'pages_show_list' and 'instagram_basic' permissions,
    or a Page Access Token.
    """
    # 1. Get User's Pages
    url = "https://graph.facebook.com/v18.0/me/accounts"
    params = {"access_token": access_token}
    resp = requests.get(url, params=params)
    data = resp.json()
    
    if "error" in data:
        raise Exception(f"Error fetching pages: {data['error']['message']}")
        
    if "data" not in data:
        raise Exception("No pages found for this user.")
        
    # 2. Find first page with an Instagram Business Account
    for page in data["data"]:
        page_id = page["id"]
        # Fetch page details to get IG ID
        page_url = f"https://graph.facebook.com/v18.0/{page_id}"
        page_params = {
            "fields": "instagram_business_account",
            "access_token": access_token
        }
        page_resp = requests.get(page_url, params=page_params)
        page_data = page_resp.json()
        
        if "instagram_business_account" in page_data:
            return page_data["instagram_business_account"]["id"]
            
    raise Exception("No Instagram Business Account found linked to your Facebook Pages.")

def post_image_to_instagram(access_token, image_url, caption, instagram_account_id=None):
    """
    Post an image to Instagram using the Graph API.
    """
    if not instagram_account_id:
        instagram_account_id = get_instagram_account_id(access_token)
    
    # Check for localhost/private URLs which Instagram cannot access
    if "localhost" in image_url or "127.0.0.1" in image_url:
        raise Exception(
            "Instagram API requires a public image URL, but a local URL was provided. "
            "Please use a tunneling tool like 'ngrok' to expose your local server, "
            "or host the images publicly. Set the BASE_URL environment variable to your public URL."
        )
        
    # 1. Create Media Container
    url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": access_token
    }
    response = requests.post(url, data=payload)
    result = response.json()
    
    if "error" in result:
        raise Exception(f"Error creating media container: {result['error']['message']}")
    
    if "id" not in result:
        raise Exception(f"Unknown error creating media container: {result}")
    
    creation_id = result["id"]
    
    # 2. Publish Media
    publish_url = f"https://graph.facebook.com/v18.0/{instagram_account_id}/media_publish"
    publish_payload = {
        "creation_id": creation_id,
        "access_token": access_token
    }
    publish_response = requests.post(publish_url, data=publish_payload)
    publish_result = publish_response.json()
    
    if "error" in publish_result:
        raise Exception(f"Error publishing media: {publish_result['error']['message']}")
        
    return publish_result.get("id")
