package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Route {
  val feeder = csv("routes.csv").random

  val view = feed(feeder).exec(
    http("View route")
      .get(C2corgConf.ui_url + "/routes/${id}/${lang}/foo")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
  )

  val advancedSearchInit = exec(
    http("Init routes advanced search")
      .get(C2corgConf.ui_url + "/routes")
      .headers(C2corgConf.header_html)
      .basicAuth(C2corgConf.basic_auth_username, C2corgConf.basic_auth_password)
    )
    .pause(500 milliseconds).exec(
    http("Default API search request")
      .get(C2corgConf.api_url + "/routes?bbox=-857237%2C3890256%2C1657236%2C7309743&pl=fr")
      .headers(C2corgConf.header_json)
    )

  val advancedSearch = exec(
    http("Routes search 1")
      .get(C2corgConf.api_url + "/routes?bbox=754868%2C5754781%2C774512%2C5781495&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(8).exec(
    http("Routes search 2")
      .get(C2corgConf.api_url + "/routes?bbox=754868%2C5754781%2C774512%2C5781495&act=mountain_climbing&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(1).exec(
    http("Routes search 3")
      .get(C2corgConf.api_url + "/routes?bbox=754868%2C5754781%2C774512%2C5781495&act=mountain_climbing%2Crock_climbing&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(4).exec(
    http("Routes search 4")
      .get(C2corgConf.api_url + "/routes?bbox=754868%2C5754781%2C774512%2C5781495&act=mountain_climbing%2Crock_climbing&rmaxa=2800%2C8850&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(5).exec(
    http("Routes search 5")
      .get(C2corgConf.api_url + "/routes?bbox=760486%2C5747022%2C780130%2C5773737&act=mountain_climbing%2Crock_climbing&rmaxa=2800%2C8850&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(20).exec(
    http("Routes search 6")
      .get(C2corgConf.api_url + "/routes?bbox=760486%2C5747022%2C780130%2C5773737&act=mountain_climbing%2Crock_climbing&rmaxa=2800%2C8850&prat=P1%2CP2&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(5).exec(
    http("Routes search 7")
      .get(C2corgConf.api_url + "/routes?bbox=760486%2C5747022%2C780130%2C5773737&act=mountain_climbing%2Crock_climbing&rmaxa=2800%2C8850&prat=P1%2CP2&frat=2%2C6a%2B&pl=fr")
      .headers(C2corgConf.header_json))
    .pause(8).exec(
    http("Routes search 8")
      .get(C2corgConf.api_url + "/routes?bbox=760486%2C5747022%2C780130%2C5773737&act=mountain_climbing%2Crock_climbing&rmaxa=2800%2C8850&prat=P1%2CP2&frat=2%2C6a%2B&offset=30&pl=fr")
      .headers(C2corgConf.header_json))
}
