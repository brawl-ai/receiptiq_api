import io
from unittest.mock import patch
import pytest
from moto import mock_aws
import pytest
from models import Project, User, Permission, SubscriptionPlan, Field, FieldType, Receipt
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from datetime import timezone, datetime, timedelta

from models.subscriptions import Payment

TEST_USER = {
    "first_name": "John",
    "last_name": "Doe", 
    "email": "kahenya0@gmail.com",
    "password": "SuperS3cr3t@Pass"
}

def create_user(db, test_settings):
    user: User = User(
        first_name=TEST_USER["first_name"],
        last_name=TEST_USER["last_name"],
        email=TEST_USER["email"],
    )
    user.set_password(TEST_USER["password"])
    for permission in db.execute(select(Permission)).scalars().all():
        user.scopes.append(permission)
    user.is_active = True
    user.is_verified = True
    db.add(user)
    db.commit()
    db.refresh(user)
    access_token = user.create_jwt_token(
                            test_settings.secret_key, 
                            algorithm=test_settings.algorithm,
                            expiry_seconds=test_settings.access_token_expiry_seconds,
                            granted_scopes=[
                                "write:projects",
                                "read:projects",
                                "delete:projects",
                                "read:fields",
                                "write:fields",
                                "delete:fields",
                                "read:receipts",
                                "write:receipts",
                                "process:projects",
                                "read:data",
                                "write:data",
                                "export:data",
                            ]
                        )
    return user, access_token

def add_subscription(db: Session, user: User):
    plan = SubscriptionPlan(
        name="Pro", 
        description="Pro", 
        plan_code="pro-code",
        price=1000, 
        currency="KES"
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    payload = {
        "event": "charge.success",
        "data": {
            "id": 1828382,
            "subscription_code": "SUB0001",
            "customer": {"email": user.email},
            "plan": {"plan_code": "pro-code"},
            "amount": 1500,
            "status": "success",
        }
    }
    data = payload["data"]
    data["subscription_plan_id"] = plan.id
    data["subscription_start_at"] = datetime.now(timezone.utc)
    data["subscription_end_at"] = datetime.now(timezone.utc) + timedelta(days=plan.days)
    payment = Payment.create_from_paystack_response(user_id=user.id, data=data)
    db.add(payment)
    db.commit()
    db.refresh(payment)

@pytest.mark.asyncio
async def test_projects(client, db, test_settings):
    user, access_token = create_user(db,test_settings)
    payload = {"name": "Test Project", "description": "Some desc"}
    add_subscription(db, user)
    response = client.post(
                        "/api/v1/projects", 
                        json=payload,
                        cookies={"access_token":access_token}
                    )
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Project"
    project = Project(name="Alpha", description="First", owner_id=user.id)
    db.add(project)
    db.commit()
    response = client.get("/api/v1/projects", cookies={"access_token":access_token})
    assert response.status_code == 200
    assert any(p["name"] == "Alpha" for p in response.json()["data"])
    response = client.get(f"/api/v1/projects/{project.id}", cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["name"] == project.name
    response = client.put(f"/api/v1/projects/{project.id}", json={"name": "Alpha1"}, cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["name"] == "Alpha1"
    response = client.delete(f"/api/v1/projects/{project.id}", cookies={"access_token":access_token})
    assert response.status_code == 204

def add_project(db:Session, user: User):
    project = Project(name="Alpha", description="First", owner_id=user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project

@pytest.mark.asyncio
async def test_fields(client, db, test_settings):
    user, access_token = create_user(db,test_settings)
    add_subscription(db,user)
    project = add_project(db, user)
    payload = {
        "name": "total_amount",
        "type": "number",
        "description": "Total amount paid"
    }
    response = client.post(f"/api/v1/projects/{project.id}/fields/", json=payload, cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["name"] == "total_amount"
    assert response.json()["type"] == "number"
    parent = Field(name="metadata", type=FieldType.OBJECT, description="meta", project_id=project.id)
    db.add(parent)
    db.commit()
    db.refresh(parent)
    payload = {
        "name": "author",
        "type": "string",
        "description": "Author Name"
    }
    response = client.post(f"/api/v1/projects/{project.id}/fields/{parent.id}/add_child", json=payload, cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["parent"]["id"] == str(parent.id)

    response = client.get(f"/api/v1/projects/{project.id}/fields/", cookies={"access_token":access_token})
    assert response.status_code == 200
    results = response.json()["data"]
    assert any(f["name"] == "author" for f in results)

    response = client.get(f"/api/v1/projects/{project.id}/fields/{parent.id}", cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["name"] == "metadata"

    payload = {"description": "Updated description for metadata"}
    response = client.put(f"/api/v1/projects/{project.id}/fields/{parent.id}", json=payload,  cookies={"access_token":access_token})
    assert response.status_code == 200
    assert response.json()["description"] == "Updated description for metadata"

    response = client.delete(f"/api/v1/projects/{project.id}/fields/{parent.id}", cookies={"access_token":access_token})
    assert response.status_code == 204

@pytest.mark.asyncio
async def test_receipts(client, db, test_settings):
    user, access_token = create_user(db,test_settings)
    add_subscription(db,user)
    project = add_project(db, user)
    headers = {"Authorization": f"Bearer {access_token}"}
    with mock_aws():
        content = io.BytesIO(b"dummy-pdf-content")
        content.name = "receipt.pdf"
        response = client.post(
            f"/api/v1/projects/{project.id}/receipts/",
            files={"file": ("receipt.pdf", content, "application/pdf")},
            cookies={"access_token":access_token}
        )
        receipt_id = response.json()["id"]
        assert response.status_code == 200
        assert response.json()["file_name"] == "receipt.pdf"
        assert response.json()["mime_type"] == "application/pdf"
        
        content = io.BytesIO(b"garbage")
        content.name = "receipt.exe"
        response = client.post(
            f"/api/v1/projects/{project.id}/receipts/",
            files={"file": ("receipt.exe", content, "application/x-msdownload")},
            cookies={"access_token":access_token}
        )
        assert response.status_code == 400
        assert "Invalid file type" in response.text

        response = client.get(f"/api/v1/projects/{project.id}/receipts/", cookies={"access_token":access_token})
        assert response.status_code == 200
        results = response.json()["data"]
        assert any(r["file_name"] == "receipt.pdf" for r in results)

        response = client.get(f"/api/v1/projects/{project.id}/receipts/{receipt_id}", cookies={"access_token":access_token})
        assert response.status_code == 200
        assert response.json()["file_name"] == "receipt.pdf"

        response = client.put(
            f"/api/v1/projects/{project.id}/receipts/{receipt_id}/",
            json={"status": "completed"},
            cookies={"access_token":access_token}
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

        response = client.put(
            f"/api/v1/projects/{project.id}/receipts/{receipt_id}/",
            json={"status": "destroyed"},
            cookies={"access_token":access_token}
        )
        assert response.status_code == 400
        assert "Invalid status" in response.text


def prepare_project(db:Session, project: Project) -> Project:
    field1 = Field(name="first_name",description="first name", type=FieldType.STRING, project_id = project.id)
    field2 = Field(name="last_name",description="last name", type=FieldType.STRING, project_id = project.id)
    field3 = Field(name="age",description="age", type=FieldType.NUMBER, project_id = project.id)
    receipt1 = Receipt(project_id=project.id,file_path="file/receipt1.pdf",file_name="receipt1.pdf",mime_type="application/pdf")
    receipt2 = Receipt(project_id=project.id,file_path="file/receipt2.pdf",file_name="receipt2.pdf",mime_type="application/pdf")
    receipt3 = Receipt(project_id=project.id,file_path="file/receipt3.pdf",file_name="receipt3.pdf",mime_type="application/pdf")
    db.add_all([field1,field2, field3])
    db.add_all([receipt1,receipt2, receipt3])
    db.commit()
    db.refresh(project)
    return project

@patch("api.data.save_csv")
@patch("utils.extractor.InvoiceExtractor.extract_from_document")
@pytest.mark.asyncio
async def test_process_project(mock_extract_from_document, mock_save_csv, client,db,test_settings):
    user, access_token = create_user(db,test_settings)
    add_subscription(db,user)
    project = add_project(db, user)
    project = prepare_project(db,project)

    mock_save_csv.return_value = io.BytesIO(b"fake,csv,data")
    mock_extract_from_document.return_value = {
        "first_name": {
            "value": "john", "coordinates":{"x":0,"y":2,"width":123,"height":85}
        },
        "last_name": {
            "value": "doe", "coordinates":{"x":0,"y":2,"width":123,"height":85}
        },
        "age": {
            "value": 29, "coordinates":{"x":0,"y":2,"width":123,"height":85}
        }
    }
    
    with mock_aws():
        response = client.post(f"/api/v1/projects/{project.id}/process", cookies={"access_token":access_token})
        data_value_id = response.json()["data"][0]["data_values"][0]["id"]
        assert response.status_code == 200
        # Data endpoints
        response = client.get(f"/api/v1/projects/{project.id}/data", cookies={"access_token":access_token})
        assert response.status_code == 200
        response = client.put(f"/api/v1/projects/{project.id}/receipts/{project.receipts[0].id}/data/{data_value_id}", cookies={"access_token":access_token}, json={"value": "a"})
        assert response.status_code == 200
        response = client.get(f"/api/v1/projects/{project.id}/data/csv", cookies={"access_token":access_token})
        assert response.status_code == 200
        # Files (Download) endpoint
        assert len(response.json()["url"]) > 0
        export_url = response.json()["url"].replace("http://testserver","")
        response = client.request("GET", export_url, cookies={"access_token":access_token}, follow_redirects=False)
        assert response.status_code == 200
        
    mock_save_csv.assert_called_once()